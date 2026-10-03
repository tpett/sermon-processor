"""A read-only stand-in for the S3 client: `get_object` on a named key and nothing else."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from sermon.cli import serves
from sermon.store.store import DATABASE_NAME

BUCKET = "reformation-recordings"
MODIFIED = datetime(2026, 8, 23, 16, 5, tzinfo=UTC)
FLAC_TYPE = "audio/flac"
SINGLE_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def refusal(code, status):
    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "GetObject",
    )


def repeating(start, length):
    return bytes((start + offset) % 251 for offset in range(length))


@dataclass
class HeldObject:
    size_bytes: int
    produces: object
    content_type: str | None
    entity_tag: str


class ReadsLazily:
    """Produces each chunk only when asked, so a 1.4 GB object costs nothing until read."""

    def __init__(self, held, start, end):
        self.held = held
        self.at = start
        self.end = end
        self.reads = []
        self.closed = False

    def read(self, amount=None):
        remaining = self.end - self.at
        taking = remaining if amount is None else min(amount, remaining)
        self.reads.append(taking)
        chunk = self.held.produces(self.at, taking)
        self.at += taking
        return chunk

    def close(self):
        self.closed = True


class HoldsBucket:
    def __init__(self):
        self.objects = {}
        self.asked = []
        self.bodies = []
        self.error = None

    def __call__(self, service, **configuration):
        return self

    def holds(self, key, payload=None, *, size_bytes=None, content_type=FLAC_TYPE):
        if payload is not None:
            body = bytes(payload)

            def produces(start, length):
                return body[start:start + length]

            size_bytes = len(body)
            tag = hashlib.md5(body).hexdigest()
        else:
            produces = repeating
            tag = hashlib.md5(f"{key}:{size_bytes}".encode()).hexdigest()
        self.objects[key] = HeldObject(size_bytes, produces, content_type, f'"{tag}"')

    def payload(self, key):
        held = self.objects[key]
        return held.produces(0, held.size_bytes)

    def lists(self):
        raise AssertionError("downloading a source must never list the bucket")

    def get_object(self, *, Bucket, Key, Range=None):
        self.asked.append({"Bucket": Bucket, "Key": Key, **({"Range": Range} if Range else {})})
        if self.error is not None:
            raise self.error
        held = self.objects.get(Key)
        if held is None:
            raise refusal("NoSuchKey", 404)
        start, end = 0, held.size_bytes
        answer = {"LastModified": MODIFIED, "ETag": held.entity_tag}
        if Range is not None:
            first, last = SINGLE_RANGE.fullmatch(Range).groups()
            if first == "":
                start = max(held.size_bytes - int(last), 0)
            else:
                start = int(first)
                end = min(int(last) + 1, held.size_bytes) if last else held.size_bytes
            if start >= held.size_bytes:
                raise refusal("InvalidRange", 416)
            answer["ContentRange"] = f"bytes {start}-{end - 1}/{held.size_bytes}"
        if held.content_type is not None:
            answer["ContentType"] = held.content_type
        body = ReadsLazily(held, start, end)
        self.bodies.append(body)
        return {**answer, "Body": body, "ContentLength": end - start}


class RecordsServer:
    def __init__(self):
        self.app = None

    def __call__(self, app, host, port):
        self.app = app


def settings_for(data_root):
    return {
        "SERMON_DATA_ROOT": str(data_root),
        "SERMON_OBJECT_STORE_ENDPOINT": "https://s3.example.invalid",
        "SERMON_OBJECT_STORE_BUCKET": BUCKET,
        "SERMON_OBJECT_STORE_ACCESS_KEY_ID": "an-access-key-id-that-is-not-real",
        "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": "a-secret-access-key-that-is-not-real",
        "SERMON_MODEL_ENDPOINT": "http://model.example.invalid:11434",
    }


def serves_as_deployed(store, bucket):
    """The app exactly as `sermon-serve` builds it, with the fake standing in for the S3 client."""
    runs = RecordsServer()
    serves(
        settings=settings_for(store.resolves_path(DATABASE_NAME).parent),
        lists_objects=bucket.lists,
        runs=runs,
        builds_client=bucket,
    )
    return runs.app
