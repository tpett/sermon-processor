import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from sermon.config import Credential, ObjectStore
from sermon.object_store import (
    ADDRESSING_STYLE,
    LISTING,
    REGION,
    SIGNATURE_VERSION,
    ListsBucketObjects,
    OpensObjectStore,
)
from sermon.reconciles_bucket import (
    ObjectStoreForbidden,
    ObjectStoreUnreachable,
    ReconcilesBucket,
)
from sermon.store import Discovery, Recording, opens_store

MODULE = Path(__file__).resolve().parents[1] / "src" / "sermon" / "object_store.py"
ENDPOINT = "https://s3.home.tpett.me"
BUCKET = "reformation-recordings"
ACCESS_KEY_ID = "an-access-key-id-that-is-not-real"
SECRET_ACCESS_KEY = "a-secret-access-key-that-is-not-real"
FROZEN = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
RECORDED = datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC)
WRITING_OPERATIONS = (
    "put_object",
    "delete_object",
    "delete_objects",
    "copy_object",
    "upload_file",
    "upload_fileobj",
    "create_multipart_upload",
    "upload_part",
    "complete_multipart_upload",
    "abort_multipart_upload",
    "put_bucket_policy",
    "create_bucket",
    "delete_bucket",
)


def configured():
    return ObjectStore(
        endpoint=ENDPOINT,
        bucket=BUCKET,
        access_key_id=Credential(ACCESS_KEY_ID),
        secret_access_key=Credential(SECRET_ACCESS_KEY),
    )


def yields_pages(pages, error):
    if error is not None:
        raise error
    yield from pages


class StubsPaginator:
    def __init__(self, pages, error):
        self.pages = pages
        self.error = error
        self.arguments = None

    def paginate(self, **arguments):
        self.arguments = arguments
        return yields_pages(self.pages, self.error)


class StubsClient:
    def __init__(self, pages=(), error=None):
        self.paginator = StubsPaginator(list(pages), error)
        self.requested = None

    def get_paginator(self, operation):
        self.requested = operation
        return self.paginator


class RecordsArguments:
    def __init__(self):
        self.positional = None
        self.keyword = None

    def __call__(self, *positional, **keyword):
        self.positional = positional
        self.keyword = keyword
        return "a client"


def entry(key, size, last_modified=None):
    return {"Key": key, "Size": size, "LastModified": last_modified or FROZEN}


def lists(pages=(), error=None):
    client = StubsClient(pages=pages, error=error)
    return client, ListsBucketObjects(bucket=BUCKET, client=client)


def forbidden(operation="ListObjectsV2"):
    return ClientError(
        {
            "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        operation,
    )


def server_error():
    return ClientError(
        {
            "Error": {"Code": "InternalError", "Message": "We encountered an error"},
            "ResponseMetadata": {"HTTPStatusCode": 500},
        },
        "ListObjectsV2",
    )


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_the_client_addresses_the_configured_endpoint_path_style_over_sigv4():
    builds = RecordsArguments()
    OpensObjectStore(object_store=configured(), builds=builds)()
    assert builds.positional == ("s3",)
    assert builds.keyword["endpoint_url"] == ENDPOINT
    assert builds.keyword["region_name"] == REGION
    assert builds.keyword["config"].signature_version == SIGNATURE_VERSION
    assert builds.keyword["config"].s3["addressing_style"] == ADDRESSING_STYLE


def test_the_client_carries_the_configured_credentials():
    builds = RecordsArguments()
    OpensObjectStore(object_store=configured(), builds=builds)()
    assert builds.keyword["aws_access_key_id"] == ACCESS_KEY_ID
    assert builds.keyword["aws_secret_access_key"] == SECRET_ACCESS_KEY


def test_no_credential_survives_into_a_representation():
    opens = OpensObjectStore(object_store=configured(), builds=RecordsArguments())
    assert ACCESS_KEY_ID not in repr(opens)
    assert SECRET_ACCESS_KEY not in repr(opens)


def test_listing_asks_the_store_for_every_page_of_the_configured_bucket():
    client, listing = lists(pages=[{"Contents": [entry("a.flac", 1)]}])
    listing()
    assert client.requested == LISTING
    assert client.paginator.arguments == {"Bucket": BUCKET}


def test_listing_reports_the_key_size_and_modification_time_of_every_object():
    modified = datetime(2026, 8, 23, 16, 5, tzinfo=UTC)
    _, listing = lists(
        pages=[
            {"Contents": [entry("recordings/recording_20260823_103015.flac", 743829120, modified)]},
            {"Contents": [entry("recordings/recording_20260816_102958.flac", 701244416, modified)]},
        ]
    )
    assert listing() == [
        {
            "object_key": "recordings/recording_20260823_103015.flac",
            "size_bytes": 743829120,
            "last_modified": modified,
        },
        {
            "object_key": "recordings/recording_20260816_102958.flac",
            "size_bytes": 701244416,
            "last_modified": modified,
        },
    ]


def test_an_empty_bucket_lists_nothing():
    _, listing = lists(pages=[{}])
    assert listing() == []


def test_a_refused_credential_is_not_a_transient_failure():
    _, listing = lists(error=forbidden())
    with pytest.raises(ObjectStoreForbidden):
        listing()


def test_an_unreachable_endpoint_is_a_transient_failure():
    _, listing = lists(error=EndpointConnectionError(endpoint_url=ENDPOINT))
    with pytest.raises(ObjectStoreUnreachable):
        listing()


def test_a_read_timeout_is_a_transient_failure():
    _, listing = lists(error=ReadTimeoutError(endpoint_url=ENDPOINT))
    with pytest.raises(ObjectStoreUnreachable):
        listing()


def test_a_server_error_is_a_transient_failure():
    _, listing = lists(error=server_error())
    with pytest.raises(ObjectStoreUnreachable):
        listing()


def test_a_transient_failure_is_not_mistaken_for_a_credential_problem():
    _, listing = lists(error=server_error())
    with pytest.raises(ObjectStoreUnreachable) as raised:
        listing()
    assert not isinstance(raised.value, ObjectStoreForbidden)


def test_reconciliation_discovers_what_the_real_client_lists(store):
    _, listing = lists(
        pages=[
            {
                "Contents": [
                    entry("recordings/recording_20260823_103015.flac", 743829120, RECORDED)
                ]
            }
        ]
    )
    ReconcilesBucket(store=store, lists_objects=listing, clock=lambda: FROZEN)()
    discovered = store.loads(Recording, "recording_20260823_103015")
    assert discovered.object_key == "recordings/recording_20260823_103015.flac"
    assert discovered.size_bytes == 743829120


def test_reconciliation_records_a_refused_credential_as_a_credential_failure(store):
    _, listing = lists(error=forbidden())
    ReconcilesBucket(store=store, lists_objects=listing, clock=lambda: FROZEN)()
    assert [scan.failure for scan in store.lists(Discovery, kind="scan")] == ["credentials"]


def test_reconciliation_records_an_unreachable_store_as_a_transient_failure(store):
    _, listing = lists(error=EndpointConnectionError(endpoint_url=ENDPOINT))
    ReconcilesBucket(store=store, lists_objects=listing, clock=lambda: FROZEN)()
    assert [scan.failure for scan in store.lists(Discovery, kind="scan")] == ["transient"]


def test_the_module_names_no_operation_that_writes():
    source = MODULE.read_text(encoding="utf-8")
    assert [verb for verb in WRITING_OPERATIONS if verb in source] == []


def test_listing_is_the_only_operation_asked_of_the_client():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    asked = sorted(
        {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "client"
        }
    )
    assert asked == ["get_paginator"]
