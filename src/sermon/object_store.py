from __future__ import annotations

from dataclasses import dataclass

REGION = "garage"
ADDRESSING_STYLE = "path"
SIGNATURE_VERSION = "s3v4"
LISTING = "list_objects_v2"


@dataclass(frozen=True)
class OpensObjectStore:
    object_store: object
    region: str = REGION
    builds: object = None

    def __call__(self):
        return None


@dataclass(frozen=True)
class ListsBucketObjects:
    bucket: str
    client: object

    def __call__(self):
        return []
