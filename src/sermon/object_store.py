from __future__ import annotations

from dataclasses import dataclass

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
ABSENT = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound", "404"})
REFUSED = 403
REFUSALS = frozenset(
    {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403", "Forbidden"}
)


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
    last_modified: object = None


@dataclass(frozen=True)
class FetchesBucketObject:
    bucket: str
    client: object
    chunk_bytes: int = CHUNK_BYTES

    def __call__(self, object_key, destination):
        raise NotImplementedError(object_key)
