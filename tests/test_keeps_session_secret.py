import os
import stat

from sermon.config import Credential
from sermon.keeps_session_secret import SECRET_FILE, KeepsSessionSecret

NAMED = "9d3b7c0e5a1f48c2b6e0d4a8f7c13e52a9b4d6f08e1c7a3b5d2f9e6c4a8b0d71"


def test_a_secret_the_deployment_names_is_the_one_used_and_nothing_is_written(tmp_path):
    assert KeepsSessionSecret(data_root=tmp_path, named=Credential(NAMED))() == NAMED
    assert list(tmp_path.iterdir()) == []


def test_without_one_a_secret_is_made_and_kept_under_the_data_root(tmp_path):
    made = KeepsSessionSecret(data_root=tmp_path, named=None)()
    assert len(made) >= 64
    assert (tmp_path / SECRET_FILE).read_text() == made


def test_the_kept_secret_is_readable_by_its_owner_alone(tmp_path):
    KeepsSessionSecret(data_root=tmp_path, named=None)()
    assert stat.S_IMODE(os.stat(tmp_path / SECRET_FILE).st_mode) == 0o600


def test_a_restart_finds_the_same_secret_so_sessions_survive_it(tmp_path):
    first = KeepsSessionSecret(data_root=tmp_path, named=None)()
    assert KeepsSessionSecret(data_root=tmp_path, named=None)() == first


def test_two_data_roots_do_not_share_a_secret(tmp_path):
    one, other = tmp_path / "one", tmp_path / "other"
    assert KeepsSessionSecret(data_root=one, named=None)() != KeepsSessionSecret(data_root=other, named=None)()


def test_a_kept_secret_left_readable_by_others_is_tightened(tmp_path):
    KeepsSessionSecret(data_root=tmp_path, named=None)()
    os.chmod(tmp_path / SECRET_FILE, 0o644)
    KeepsSessionSecret(data_root=tmp_path, named=None)()
    assert stat.S_IMODE(os.stat(tmp_path / SECRET_FILE).st_mode) == 0o600


def test_an_empty_kept_file_is_not_a_secret_and_is_replaced(tmp_path):
    (tmp_path / SECRET_FILE).write_text("")
    made = KeepsSessionSecret(data_root=tmp_path, named=None)()
    assert made and (tmp_path / SECRET_FILE).read_text() == made
