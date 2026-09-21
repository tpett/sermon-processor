from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from sermon.config import ObjectStore
from sermon.reconciles_bucket import ObjectStoreForbidden, ObjectStoreUnreachable

REGION = "garage"
ADDRESSING_STYLE = "path"
SIGNATURE_VERSION = "s3v4"
LISTING = "list_objects_v2"
READING = "get_object"
CHUNK_BYTES = 8 * 1024 * 1024
MULTIPART = "-"
DIGEST_LENGTH = 32
ABSENT_STATUS = 404
ABSENT = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound", "404"})
REFUSED = 403
REFUSALS = frozenset(
    {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403", "Forbidden"}
)


def cannot_find_the_object(error):
    response = error.response or {}
    return (
        response.get("ResponseMetadata", {}).get("HTTPStatusCode") == ABSENT_STATUS
        or response.get("Error", {}).get("Code") in ABSENT
    )


def reads_a_plain_digest(entity_tag):
    unquoted = (entity_tag or "").strip('"')
    if len(unquoted) != DIGEST_LENGTH or MULTIPART in unquoted:
        return None
    try:
        int(unquoted, 16)
    except ValueError:
        return None
    return unquoted


def refuses_the_credential(error):
    response = error.response or {}
    return (
        response.get("ResponseMetadata", {}).get("HTTPStatusCode") == REFUSED
        or response.get("Error", {}).get("Code") in REFUSALS
    )


def translates(error):
    if isinstance(error, ClientError) and refuses_the_credential(error):
        return ObjectStoreForbidden(str(error))
    return ObjectStoreUnreachable(str(error))


@dataclass(frozen=True)
class OpensObjectStore:
    object_store: ObjectStore
    region: str = REGION
    builds: object = None

    def __call__(self):
        builds = boto3.client if self.builds is None else self.builds
        return builds(
            "s3",
            endpoint_url=self.object_store.endpoint,
            region_name=self.region,
            aws_access_key_id=self.object_store.access_key_id.reveals(),
            aws_secret_access_key=self.object_store.secret_access_key.reveals(),
            config=Config(
                signature_version=SIGNATURE_VERSION,
                s3={"addressing_style": ADDRESSING_STYLE},
            ),
        )


@dataclass(frozen=True)
class ListsBucketObjects:
    bucket: str
    client: object

    def __call__(self):
        try:
            return [
                {
                    "object_key": item["Key"],
                    "size_bytes": item["Size"],
                    "last_modified": item["LastModified"],
                }
                for page in self.client.get_paginator(LISTING).paginate(Bucket=self.bucket)
                for item in page.get("Contents", ())
            ]
        except (BotoCoreError, ClientError) as error:
            raise translates(error) from error


@dataclass(frozen=True)
class FetchedObject:
    size_bytes: int
    announced_bytes: int | None = None
    checksum: str | None = None
    entity_tag: str | None = None
    last_modified: datetime | None = None


@dataclass(frozen=True)
class FetchesBucketObject:
    bucket: str
    client: object
    chunk_bytes: int = CHUNK_BYTES

    def __call__(self, object_key, destination):
        try:
            answer = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except ClientError as error:
            if cannot_find_the_object(error):
                return None
            raise translates(error) from error
        except BotoCoreError as error:
            raise translates(error) from error
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.md5()
        written = 0
        with answer["Body"] as body, destination.open("wb") as sink:
            while chunk := body.read(self.chunk_bytes):
                digest.update(chunk)
                written += len(chunk)
                sink.write(chunk)
        return FetchedObject(
            size_bytes=written,
            announced_bytes=answer.get("ContentLength"),
            checksum=digest.hexdigest(),
            entity_tag=reads_a_plain_digest(answer.get("ETag")),
            last_modified=answer.get("LastModified"),
        )
