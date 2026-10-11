"""Unit tests for the data models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from recursivegitupdate.models import CACHE_VERSION, CacheData, FolderCandidates, Results


class TestFolderCandidates:
    @staticmethod
    def test_creation():
        fc = FolderCandidates(git=[], svn=[], ignores=[])
        assert fc.git == ()
        assert fc.svn == ()
        assert fc.ignores == ()
        assert fc.git_nopush == ()

    @staticmethod
    def test_defaults():
        assert FolderCandidates() == FolderCandidates(git=[], svn=[], ignores=[], git_nopush=[])

    @staticmethod
    def test_accepts_lists_and_converts_to_tuples():
        fc = FolderCandidates(git=[Path("/a")], svn=[Path("/b")], ignores=[Path("/c")], git_nopush=[Path("/a")])
        assert isinstance(fc.git, tuple)
        assert isinstance(fc.svn, tuple)
        assert isinstance(fc.ignores, tuple)
        assert isinstance(fc.git_nopush, tuple)

    @staticmethod
    def test_accepts_tuples():
        fc = FolderCandidates(git=(Path("/a"),), svn=(), ignores=())
        assert fc.git == (Path("/a"),)

    @staticmethod
    def test_converts_strings_to_paths():
        fc = FolderCandidates(git=["/a"])
        assert fc.git == (Path("/a"),)

    @staticmethod
    def test_frozen_attribute_reassignment():
        fc = FolderCandidates()
        with pytest.raises(ValidationError):
            fc.git = (Path("/foo"),)

    @staticmethod
    def test_frozen_content_immutable():
        """Tuple contents cannot be mutated (no append)."""
        fc = FolderCandidates(git=[Path("/a")])
        with pytest.raises(AttributeError):
            fc.git.append(Path("/b"))

    @staticmethod
    def test_equality():
        assert FolderCandidates(git=[Path("/a")]) == FolderCandidates(git=[Path("/a")])

    @staticmethod
    def test_equality_list_vs_tuple_input():
        """Same data, different input types → equal."""
        assert FolderCandidates(git=[Path("/a")]) == FolderCandidates(git=(Path("/a"),))

    @staticmethod
    def test_inequality():
        assert FolderCandidates(git=[Path("/a")]) != FolderCandidates(git=[Path("/b")])


class TestCacheData:
    @staticmethod
    def test_defaults(tmp_path):
        data = CacheData(root=tmp_path, candidates=FolderCandidates())
        assert data.root == tmp_path
        assert data.cache_version == CACHE_VERSION

    @staticmethod
    def test_missing_fields_are_rejected(tmp_path):
        with pytest.raises(ValidationError):
            CacheData()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            CacheData(root=tmp_path)  # type: ignore[call-arg]

    @staticmethod
    def test_equality(tmp_path):
        fc = FolderCandidates(git=[Path("/a")])
        assert CacheData(root=tmp_path, candidates=fc) == CacheData(root=tmp_path, candidates=fc)
        assert CacheData(root=tmp_path, candidates=fc) != CacheData(root=tmp_path, candidates=FolderCandidates())

    @staticmethod
    def test_json_roundtrip(tmp_path):
        data = CacheData(root=tmp_path, candidates=FolderCandidates(git=[Path("/a")], git_nopush=[Path("/a")]))
        assert CacheData.model_validate_json(data.model_dump_json()) == data

    @staticmethod
    def test_accepts_layout_without_git_nopush(tmp_path):
        """Cache files written before ``git_nopush`` existed are still readable."""
        data = CacheData.model_validate_json(
            f'{{"root": "{tmp_path}", "candidates": {{"git": ["/a"], "svn": [], "ignores": []}}, "cache_version": 4}}'
        )
        assert data.candidates == FolderCandidates(git=[Path("/a")])


class TestResults:
    @staticmethod
    def test_creation():
        r = Results()
        assert r.ok == {}
        assert r.error == {}
        assert r.ignored == {}

    @staticmethod
    def test_instances_are_independent():
        """Ensure separate instances don't share mutable state."""
        r1 = Results()
        r2 = Results()
        r1.ok[Path("/foo")] = "test"
        assert Path("/foo") not in r2.ok

    @staticmethod
    def test_mutability():
        r = Results()
        r.ok[Path("/a")] = "ok"
        r.error[Path("/b")] = "fail"
        r.ignored[Path("/c")] = "ignored"
        assert len(r.ok) == 1
        assert len(r.error) == 1
        assert len(r.ignored) == 1

    @staticmethod
    def test_has_errors_false():
        r = Results()
        r.ok[Path("/a")] = "ok"
        assert r.has_errors is False

    @staticmethod
    def test_has_errors_true():
        r = Results()
        r.error[Path("/a")] = "fail"
        assert r.has_errors is True
