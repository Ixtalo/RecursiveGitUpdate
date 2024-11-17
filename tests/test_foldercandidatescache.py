# -*- coding: utf-8 -*-
"""Unit tests."""
import logging
from pathlib import Path

import pytest

from recursivegitupdate.foldercandidatescache import FolderCandidatesCache, CacheData

# pylint: disable=missing-function-docstring,missing-class-docstring


def test_cachedata(tmp_path):
    # noinspection PyTypeChecker
    actual = CacheData(root=tmp_path, candidates="foo", cache_version="foo")
    assert actual.root == tmp_path
    assert actual.candidates == "foo"
    assert actual.cache_version == "foo"
    # invalid calls
    with pytest.raises(TypeError):
        # pylint: disable=no-value-for-parameter
        # noinspection PyArgumentList
        CacheData()
    with pytest.raises(TypeError):
        # pylint: disable=no-value-for-parameter
        # noinspection PyArgumentList
        CacheData(root=tmp_path)


# noinspection PyTypeChecker
def test_cachedata_compare(tmp_path):
    actual1 = CacheData(root=tmp_path, candidates="foo", cache_version="foo")
    actual2 = CacheData(root=tmp_path, candidates="foo", cache_version="foo")
    assert actual1 == actual2
    # unequal
    actual2 = CacheData(root=tmp_path, candidates="foo2", cache_version="foo")
    assert actual1 != actual2


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
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]})
    # action
    cache = FolderCandidatesCache(cache_file=cache_file)
    cache.update(data)
    # check
    assert cache_file.exists()
    assert caplog.messages[2] == 'Updating cache ...'
    with cache_file.open("r", encoding="utf8") as fin:
        content = fin.read()
    assert content == """{
    "root": "%s",
    "candidates": {
        "foo": [
            "bar"
        ]
    },
    "cache_version": 3
}""" % tmp_path.resolve()


def test_load(tmp_path):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]})
    cache.update(data)
    # action
    actual = cache.load()
    assert actual == data


def test_load_isoutdated(tmp_path, monkeypatch, caplog):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    monkeypatch.setattr(FolderCandidatesCache, "get_age",
                        lambda _: cache.outdated_age_max_days + 1)
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]})
    cache.update(data)
    # action
    actual = cache.load()
    # check
    assert not actual
    assert caplog.messages[0] == 'Cache is outdated!'


def test_load_nonexistent(tmp_path):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]})
    cache.update(data)
    # remove
    cache_file.unlink()
    # action
    actual = cache.load()
    # check
    assert not actual


def test_check_version__invalid_version(tmp_path):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    # noinspection PyTypeChecker
    invalid_version_nonumber = "foo"
    # noinspection PyTypeChecker
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]}, cache_version=invalid_version_nonumber)
    cache.update(data)
    # action
    with pytest.raises(RuntimeError) as ex:
        cache.load()
    # check
    assert str(ex) == ("<ExceptionInfo RuntimeError('Invalid cache - could not read version field!', "
                       'ValueError("invalid literal for int() with base 10: \'foo\'")) tblen=3>')


def test_check_version_unequal(tmp_path):
    # prepare
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]}, cache_version=999)
    cache.update(data)
    # action
    with pytest.raises(RuntimeError) as ex:
        cache.load()
    # check
    assert str(ex) == "<ExceptionInfo RuntimeError('Invalid cache version! expected:3, actual:999') tblen=3>"


def test_invalidate(tmp_path, caplog):
    # prepare
    caplog.set_level(logging.INFO)
    cache_file = tmp_path.joinpath("testache.json")
    cache = FolderCandidatesCache(cache_file=cache_file)
    data = CacheData(root=tmp_path, candidates={"foo": [Path("bar")]})
    cache.update(data)
    # action
    cache.invalidate()
    # check
    assert not cache_file.exists()
    assert caplog.messages[0] == 'Updating cache ...'
    assert caplog.messages[1] == 'Invalidating cache by removing cache file.'
