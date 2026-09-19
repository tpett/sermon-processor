from pathlib import Path

import pytest

from sermon.store import DEFAULT_DATA_ROOT, PathEscapesDataRoot, ResolvesStoredPath

STORED = "recording_20260913_090014/2026-09-13 - Hebrews 12.mp3"


def test_the_data_root_is_injected_with_a_default():
    assert ResolvesStoredPath().data_root == DEFAULT_DATA_ROOT
    assert ResolvesStoredPath(data_root=Path("/srv/sermons")).data_root == Path("/srv/sermons")


def test_a_stored_path_resolves_under_the_data_root(tmp_path):
    assert ResolvesStoredPath(data_root=tmp_path)(STORED) == tmp_path / STORED


def test_a_path_that_climbs_and_comes_back_resolves_where_it_lands(tmp_path):
    resolved = ResolvesStoredPath(data_root=tmp_path)("recording/../transcripts/one.json")
    assert resolved == tmp_path / "transcripts/one.json"


@pytest.mark.parametrize(
    "path",
    [
        "../escaped.mp3",
        "../../etc/passwd",
        "recording_20260913_090014/../../escaped.mp3",
        "./../escaped.mp3",
    ],
)
def test_a_path_that_climbs_out_of_the_data_root_is_refused(tmp_path, path):
    with pytest.raises(PathEscapesDataRoot):
        ResolvesStoredPath(data_root=tmp_path)(path)


def test_an_absolute_path_is_refused_even_when_it_points_inside(tmp_path):
    resolves = ResolvesStoredPath(data_root=tmp_path)
    with pytest.raises(PathEscapesDataRoot):
        resolves("/etc/passwd")
    with pytest.raises(PathEscapesDataRoot):
        resolves(str(tmp_path / STORED))


def test_a_symlink_that_leads_out_of_the_data_root_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "elsewhere").mkdir()
    (root / "renders").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(PathEscapesDataRoot):
        ResolvesStoredPath(data_root=root)("renders/escaped.mp3")


def test_the_data_root_itself_is_not_an_artifact_path(tmp_path):
    with pytest.raises(PathEscapesDataRoot):
        ResolvesStoredPath(data_root=tmp_path)("")
