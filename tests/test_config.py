import logging
import os
import socket
from dataclasses import fields
from pathlib import Path

import pytest

from sermon.config import (
    VARIABLES,
    Configuration,
    Credential,
    MissingConfiguration,
    ModelEndpointUnreachable,
    ObjectStore,
    ReachesModelEndpoint,
    ReadsConfiguration,
    UnusableConfiguration,
)

MODEL_ENDPOINT = "http://mac-m1:11434"
OBJECT_STORE_ENDPOINT = "https://s3.home.tpett.me"
BUCKET = "reformation-recordings"
ACCESS_KEY_ID = "GK7d41f0b3c2a94e6581d7b2ff"
SECRET_ACCESS_KEY = "b892c0665f0a4d1e9c3aa71e5f4d8c02b6e97a35"

ENVIRONMENT = {
    "SERMON_DATA_ROOT": "/srv/sermons",
    "SERMON_OBJECT_STORE_ENDPOINT": OBJECT_STORE_ENDPOINT,
    "SERMON_OBJECT_STORE_BUCKET": BUCKET,
    "SERMON_OBJECT_STORE_ACCESS_KEY_ID": ACCESS_KEY_ID,
    "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": SECRET_ACCESS_KEY,
    "SERMON_MODEL_ENDPOINT": MODEL_ENDPOINT,
}

NOT_HTTP = ["ssh://mac-m1", "scp://mac-m1", "mac-m1:11434", "file:///models", "ftp://mac-m1/"]

UNANSWERED = [
    ConnectionRefusedError(61, "Connection refused"),
    TimeoutError("timed out"),
    socket.gaierror(8, "nodename nor servname provided"),
    OSError(65, "No route to host"),
]


def configured(**overrides):
    return ReadsConfiguration(environment=ENVIRONMENT | overrides)()


def object_store(**overrides):
    return ObjectStore(
        **{
            "endpoint": OBJECT_STORE_ENDPOINT,
            "bucket": BUCKET,
            "access_key_id": Credential(ACCESS_KEY_ID),
            "secret_access_key": Credential(SECRET_ACCESS_KEY),
        }
        | overrides
    )


def test_the_configuration_is_read_from_exactly_the_variables_it_declares():
    assert set(VARIABLES) == set(ENVIRONMENT)


def test_the_data_root_the_object_store_and_the_model_endpoint_come_from_the_environment():
    configuration = configured()
    assert configuration.data_root == Path("/srv/sermons")
    assert configuration.object_store.endpoint == OBJECT_STORE_ENDPOINT
    assert configuration.object_store.bucket == BUCKET
    assert configuration.object_store.access_key_id.reveals() == ACCESS_KEY_ID
    assert configuration.object_store.secret_access_key.reveals() == SECRET_ACCESS_KEY
    assert configuration.model_endpoint == MODEL_ENDPOINT


def test_the_environment_it_reads_defaults_to_the_one_the_process_was_given():
    assert ReadsConfiguration().environment is os.environ


def test_a_substituted_model_endpoint_needs_no_change_to_the_process_environment():
    substitute = "http://127.0.0.1:1/"
    assert configured(SERMON_MODEL_ENDPOINT=substitute).model_endpoint == substitute
    assert "SERMON_MODEL_ENDPOINT" not in os.environ


def test_nothing_defaults_a_configuration_value():
    with pytest.raises(TypeError):
        Configuration()


@pytest.mark.parametrize("name", VARIABLES)
def test_an_unset_variable_is_named_rather_than_defaulted(name):
    absent = {key: value for key, value in ENVIRONMENT.items() if key != name}
    with pytest.raises(MissingConfiguration) as refused:
        ReadsConfiguration(environment=absent)()
    assert name in str(refused.value)


@pytest.mark.parametrize("name", VARIABLES)
def test_a_variable_set_to_nothing_is_as_absent_as_one_never_set(name):
    with pytest.raises(MissingConfiguration) as refused:
        configured(**{name: ""})
    assert name in str(refused.value)


@pytest.mark.parametrize("root", ["data", "./data", "recordings/2026"])
def test_a_data_root_that_depends_on_the_working_directory_is_refused(root):
    with pytest.raises(UnusableConfiguration) as refused:
        configured(SERMON_DATA_ROOT=root)
    assert str(Path(root)) in str(refused.value)


def test_a_data_root_that_is_not_a_path_is_refused():
    with pytest.raises(UnusableConfiguration):
        Configuration(
            data_root="/srv/sermons", object_store=object_store(), model_endpoint=MODEL_ENDPOINT
        )


@pytest.mark.parametrize("endpoint", NOT_HTTP)
def test_a_model_endpoint_reached_over_anything_but_http_is_refused(endpoint):
    with pytest.raises(UnusableConfiguration) as refused:
        configured(SERMON_MODEL_ENDPOINT=endpoint)
    assert endpoint in str(refused.value)


@pytest.mark.parametrize("endpoint", NOT_HTTP)
def test_an_object_store_endpoint_reached_over_anything_but_http_is_refused(endpoint):
    with pytest.raises(UnusableConfiguration) as refused:
        configured(SERMON_OBJECT_STORE_ENDPOINT=endpoint)
    assert endpoint in str(refused.value)


@pytest.mark.parametrize("endpoint", ["http://", "https://"])
def test_an_endpoint_that_names_no_host_is_refused(endpoint):
    with pytest.raises(UnusableConfiguration):
        configured(SERMON_MODEL_ENDPOINT=endpoint)


@pytest.mark.parametrize("endpoint", ["http://mac-m1:11434", "https://mac-m1:11434/v1"])
def test_a_model_endpoint_reached_over_http_is_accepted(endpoint):
    assert configured(SERMON_MODEL_ENDPOINT=endpoint).model_endpoint == endpoint


def test_a_credential_yields_its_value_only_when_it_is_asked():
    assert Credential(SECRET_ACCESS_KEY).reveals() == SECRET_ACCESS_KEY
    assert Credential(SECRET_ACCESS_KEY) == Credential(SECRET_ACCESS_KEY)
    assert Credential(SECRET_ACCESS_KEY) != Credential(ACCESS_KEY_ID)


def test_no_credential_reaches_a_repr_or_a_log_line(caplog):
    configuration = configured()
    with caplog.at_level(logging.INFO):
        logging.getLogger("sermon").info("%s %r", configuration, configuration.object_store)
    for rendered in (
        repr(configuration),
        str(configuration),
        repr(configuration.object_store),
        str(configuration.object_store.secret_access_key),
        f"{configuration.object_store.access_key_id}",
        caplog.text,
    ):
        assert ACCESS_KEY_ID not in rendered
        assert SECRET_ACCESS_KEY not in rendered


@pytest.mark.parametrize("name", ["access_key_id", "secret_access_key"])
def test_an_object_store_refuses_a_credential_that_would_print_itself(name):
    with pytest.raises(UnusableConfiguration) as refused:
        object_store(**{name: SECRET_ACCESS_KEY})
    assert SECRET_ACCESS_KEY not in str(refused.value)


def test_nothing_configures_a_credential_for_the_machine_serving_the_model():
    configuration = configured()
    assert [
        name for name, value in vars(configuration).items() if isinstance(value, Credential)
    ] == []
    assert {declared.name for declared in fields(ReachesModelEndpoint)} == {"endpoint", "over"}


@pytest.mark.parametrize("unanswered", UNANSWERED, ids=lambda one: type(one).__name__)
def test_an_endpoint_that_does_not_answer_is_named_rather_than_the_model(unanswered):
    def does_not_answer(endpoint):
        raise unanswered

    with pytest.raises(ModelEndpointUnreachable) as unreachable:
        ReachesModelEndpoint(endpoint=MODEL_ENDPOINT, over=does_not_answer)()
    assert MODEL_ENDPOINT in str(unreachable.value)
    assert unreachable.value.endpoint == MODEL_ENDPOINT
    assert unreachable.value.__cause__ is unanswered


def test_the_endpoint_a_test_substitutes_is_the_one_reached():
    reached = []
    substitute = "http://127.0.0.1:1/"
    ReachesModelEndpoint(endpoint=substitute, over=reached.append)()
    assert reached == [substitute]


def test_an_answer_from_the_endpoint_is_returned_as_it_came():
    answered = ReachesModelEndpoint(endpoint=MODEL_ENDPOINT, over=lambda endpoint: {"models": []})
    assert answered() == {"models": []}


@pytest.mark.parametrize("endpoint", NOT_HTTP)
def test_the_model_endpoint_cannot_be_reached_over_anything_but_http(endpoint):
    with pytest.raises(UnusableConfiguration):
        ReachesModelEndpoint(endpoint=endpoint, over=lambda reached: None)
