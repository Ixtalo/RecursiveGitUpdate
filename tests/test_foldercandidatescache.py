"""Unit tests."""

import logging
import os
import tempfile
from pathlib import Path

import pytest

from recursivegitupdate import foldercandidatescache
from recursivegitupdate.foldercandidatescache import FolderCandidatesCache
from recursivegitupdate.models import CACHE_VERSION, CacheData, FolderCandidates

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions and ownership")


def _make_data(root: Path, **kwargs) -> CacheData:
    return CacheData(root=root, candidates=FolderCandidates(git=[Path("bar")]), **kwargs)


def test_constructor(tmp_path, caplog):
    # prepare
    caplog.set_level(logging.DEBUG)
    cache_file = tmp_path.joinpath("testache.json")
    # action
    FolderCandidatesCache(cache_file=cache_file)
    # check
    assert not cache_file.exists()
    assert caplog.messages[0] == f"cache_file: {cache_file.resolve()}"
    assert caplog.messages[1] == "outdated_age_max_days: 1.00"


def test_update(tmp_path, caplog):
    # prepare
    caplog.set_level(logging.DEBUG)
    cache_file = tmp_path.joinpath("testache.json")
    data = _make_data(tmp_path)
    # action
    cache = FolderCandidatesCache(cache_file=cache_file)
    cache.update(data)
    # check
    assert cache_file.exists()
    assert caplog.messages[2] == "Updating cache ..."
    expected = f"""{{
    "root": "{tmp_path.resolve()}",
    "candidates": {{
        "git": [
            "bar"
        ],
        "svn": [],
        "ignores": [],
        "git_nopush": []
    }},
    "cache_version": {CACHE_VERSION}
}}"""
    assert cache_file.read_text(encoding="utf8") == expected


def test_update_leaves_no_temp_files(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache = FolderCandidatesCache(cache_file=cache_dir / "testache.json")
    cache.update(_make_data(tmp_path))
    cache.update(_make_data(tmp_path))
    assert [p.name for p in cache_dir.iterdir()] == ["testache.json"]


def test_update_failure_is_only_a_warning(tmp_path, monkeypatch, caplog):
    """The cache is an optimization: write errors must neither abort nor leave temp files behind."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "testache.json"

    def _fail(_self, _target):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", _fail)
    # action
    FolderCandidatesCache(cache_file=cache_file).update(_make_data(tmp_path))
    # check
    assert not any(cache_dir.iterdir())
    assert any("Failed to write cache file" in msg and "locked" in msg for msg in caplog.messages)


def test_update_without_cache_dir_is_only_a_warning(tmp_path, caplog):
    cache = FolderCandidatesCache(cache_file=tmp_path / "missing" / "testache.json")
    cache.update(_make_data(tmp_path))
    assert any("Failed to write cache file" in msg for msg in caplog.messages)


def test_load(tmp_path):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    data = _make_data(tmp_path)
    cache.update(data)
    # action
    actual = cache.load()
    assert actual == data
    assert isinstance(actual.candidates.git[0], Path)


def test_load_isoutdated(tmp_path, monkeypatch, caplog):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    monkeypatch.setattr(FolderCandidatesCache, "get_age", lambda _: cache.outdated_age_max_days + 1)
    cache.update(_make_data(tmp_path))
    # action
    actual = cache.load()
    # check
    assert not actual
    assert caplog.messages[0] == "Cache is outdated!"


def test_load_nonexistent(tmp_path):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    cache.update(_make_data(tmp_path))
    # remove
    cache_file.unlink()
    # action
    actual = cache.load()
    # check
    assert not actual


def test_load_unequal_version_is_ignored(tmp_path, caplog):
    """A cache file written by another program version is treated as missing."""
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    cache.update(_make_data(tmp_path, cache_version=999))
    # action
    actual = cache.load()
    # check
    assert actual is None
    assert any(f"expected: {CACHE_VERSION}, actual: 999" in msg for msg in caplog.messages)


def test_load_invalid_version_field(tmp_path, caplog):
    """A non-numeric version field makes the file invalid."""
    cache_file = tmp_path.joinpath("testache.json")
    cache_file.write_text(f'{{"root": "{tmp_path}", "candidates": {{}}, "cache_version": "foo"}}', encoding="utf8")
    cache = FolderCandidatesCache(cache_file=cache_file)
    # action
    actual = cache.load()
    # check
    assert actual is None
    assert any("Failed to read cache file" in msg for msg in caplog.messages)


def test_load_file_without_git_nopush(tmp_path):
    """Cache files written before the no-push marker existed are still readable."""
    cache_file = tmp_path.joinpath("testache.json")
    cache_file.write_text(
        f'{{"root": "{tmp_path}", "candidates": {{"git": ["/work/a"], "svn": [], "ignores": []}}, '
        f'"cache_version": {CACHE_VERSION}}}',
        encoding="utf8",
    )
    # action
    actual = FolderCandidatesCache(cache_file=cache_file).load()
    # check
    assert actual is not None
    assert actual.candidates.git == (Path("/work/a"),)
    assert actual.candidates.git_nopush == ()


def test_invalidate(tmp_path, caplog):
    # prepare
    caplog.set_level(logging.INFO)
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    cache.update(_make_data(tmp_path))
    # action
    cache.invalidate()
    # check
    assert not cache_file.exists()
    assert caplog.messages[0] == "Updating cache ..."
    assert caplog.messages[1] == "Invalidating cache by removing cache file."


def test_load_corrupt_json(tmp_path, caplog):
    """Corrupt JSON file is handled gracefully."""
    caplog.set_level(logging.DEBUG)
    cache_file = tmp_path / "testcache.json"
    cache_file.write_text("{invalid json!!!", encoding="utf8")
    cache = FolderCandidatesCache(cache_file=cache_file)
    # action
    actual = cache.load()
    # check
    assert actual is None
    assert any("Failed to read cache file" in msg for msg in caplog.messages)


def test_load_invalid_encoding(tmp_path, caplog):
    """A file which is not valid UTF-8 is handled gracefully."""
    cache_file = tmp_path / "testcache.json"
    cache_file.write_bytes(b"\xff\xfe\x00garbage")
    cache = FolderCandidatesCache(cache_file=cache_file)
    # action
    actual = cache.load()
    # check
    assert actual is None
    assert any("Failed to read cache file" in msg for msg in caplog.messages)


def test_load_missing_keys(tmp_path, caplog):
    """JSON with missing keys is handled gracefully."""
    caplog.set_level(logging.DEBUG)
    cache_file = tmp_path / "testcache.json"
    cache_file.write_text('{"root": "/tmp"}', encoding="utf8")
    cache = FolderCandidatesCache(cache_file=cache_file)
    # action
    actual = cache.load()
    # check
    assert actual is None
    assert any("Failed to read cache file" in msg and "candidates" in msg for msg in caplog.messages)


# ============================================================
# for_basepath (location in the temp directory)
# ============================================================


class TestForBasepath:
    @staticmethod
    def test_file_is_located_in_temp_dir(tmp_path):
        basepath = tmp_path / "base"
        basepath.mkdir()
        cache = FolderCandidatesCache.for_basepath(basepath, outdated_age_max_days=2.5)
        assert cache.enabled
        assert cache.outdated_age_max_days == 2.5
        assert cache.cache_filepath.parent.parent == Path(tempfile.gettempdir())
        assert cache.cache_filepath.parent.name.startswith("recursivegitupdate-")
        assert cache.cache_filepath.parent.is_dir()
        assert cache.cache_filepath.suffix == ".json"
        assert not cache.cache_filepath.exists()

    @staticmethod
    def test_file_name_depends_on_basepath(tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        path_a = FolderCandidatesCache.for_basepath(tmp_path / "a").cache_filepath
        assert path_a == FolderCandidatesCache.for_basepath(tmp_path / "a").cache_filepath
        assert path_a == FolderCandidatesCache.for_basepath(tmp_path / "a" / ".." / "a").cache_filepath
        assert path_a != FolderCandidatesCache.for_basepath(tmp_path / "b").cache_filepath

    @staticmethod
    def test_roundtrip(tmp_path):
        cache = FolderCandidatesCache.for_basepath(tmp_path)
        data = _make_data(tmp_path)
        cache.update(data)
        assert FolderCandidatesCache.for_basepath(tmp_path).load() == data

    @staticmethod
    def test_user_name_is_sanitized(monkeypatch):
        monkeypatch.setattr(foldercandidatescache.getpass, "getuser", lambda: r"DOMAIN\john doe/../x")
        assert foldercandidatescache._user_name() == "DOMAIN_john_doe_.._x"

    @staticmethod
    def test_user_name_fallback(monkeypatch):
        def _fail():
            raise KeyError("no passwd entry")

        monkeypatch.setattr(foldercandidatescache.getpass, "getuser", _fail)
        assert foldercandidatescache._user_name()  # never empty

    @staticmethod
    @posix_only
    def test_cache_dir_is_private(tmp_path):
        cache = FolderCandidatesCache.for_basepath(tmp_path)
        assert cache.cache_filepath.parent.stat().st_mode & 0o777 == 0o700

    @staticmethod
    @posix_only
    def test_too_open_cache_dir_is_tightened(tmp_path):
        cache_dir = FolderCandidatesCache.for_basepath(tmp_path).cache_filepath.parent
        cache_dir.chmod(0o755)
        cache = FolderCandidatesCache.for_basepath(tmp_path)
        assert cache.enabled
        assert cache_dir.stat().st_mode & 0o777 == 0o700

    @staticmethod
    @posix_only
    def test_symlinked_cache_dir_disables_cache(tmp_path, caplog):
        cache_dir = FolderCandidatesCache.for_basepath(tmp_path).cache_filepath.parent
        cache_dir.rmdir()
        target = tmp_path / "elsewhere"
        target.mkdir()
        cache_dir.symlink_to(target, target_is_directory=True)
        # action
        cache = FolderCandidatesCache.for_basepath(tmp_path)
        # check
        assert not cache.enabled
        assert any("not a real directory" in msg for msg in caplog.messages)
        cache.update(_make_data(tmp_path))
        assert not any(target.iterdir())
        assert cache.load() is None

    @staticmethod
    @posix_only
    def test_foreign_owner_disables_cache(tmp_path, monkeypatch, caplog):
        FolderCandidatesCache.for_basepath(tmp_path)  # creates the directory
        real_uid = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)  # as if the directory were owned by somebody else
        # action
        cache = FolderCandidatesCache.for_basepath(tmp_path)
        # check
        assert not cache.enabled
        assert any("belongs to another user" in msg for msg in caplog.messages)

    @staticmethod
    def test_disabled_cache_is_inert(tmp_path):
        cache_file = tmp_path / "testache.json"
        cache = FolderCandidatesCache(cache_file=cache_file, enabled=False)
        cache.update(_make_data(tmp_path))
        assert not cache_file.exists()
        cache_file.write_text("{}", encoding="utf8")
        assert cache.load() is None
        cache.invalidate()
        assert cache_file.exists()
