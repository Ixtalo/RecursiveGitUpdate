"""Unit tests for git_utils module."""

import logging
from subprocess import CalledProcessError

import pytest

from recursivegitupdate.utils.git_utils import call_git, check_git_pullpush, extract_origin_push_url, get_git_cmd
from tests.utilities import git_add_remote, git_disable_push, git_init


class TestGitCmd:
    @staticmethod
    def test_git_cmd_is_found():
        """get_git_cmd() should return a non-empty string pointing to an existing binary."""
        result = get_git_cmd()
        assert result
        assert "git" in result


class TestExtractOriginPushUrl:
    @staticmethod
    def test_empty_string():
        assert extract_origin_push_url("") is None

    @staticmethod
    def test_garbage():
        assert extract_origin_push_url("foobar") is None

    @staticmethod
    def test_single_origin():
        assert extract_origin_push_url("origin bla (push)") == "bla"

    @staticmethod
    def test_multiple_remotes():
        output = "origin bla (push)\nother foo (push)"
        assert extract_origin_push_url(output) == "bla"

    @staticmethod
    def test_duplicate_origin():
        output = "origin bla (push)\norigin foo (push)"
        assert extract_origin_push_url(output) == "bla"

    @staticmethod
    def test_fetch_only():
        output = "origin bla (fetch)"
        assert extract_origin_push_url(output) is None

    @staticmethod
    def test_non_origin_push():
        output = "upstream bla (push)"
        assert extract_origin_push_url(output) is None

    @staticmethod
    @pytest.mark.parametrize(
        "url",
        [
            "ssh://git@server/repo.git",
            "https://gitlab.com/user/repo.git",
            "file:///local/path",
            "git@github.com:user/repo.git",
        ],
    )
    def test_various_url_formats(url):
        """Extracts push URL regardless of format."""
        output = f"origin {url} (push)\norigin {url} (fetch)"
        assert extract_origin_push_url(output) == url


class TestCheckGitPullPush:
    @staticmethod
    def test_no_git_dir(tmp_path):
        with pytest.raises(CalledProcessError):
            check_git_pullpush(tmp_path)

    @staticmethod
    def test_no_remote(tmp_path):
        git_init(tmp_path)
        actual = check_git_pullpush(tmp_path)
        assert actual == (False, False, None)

    @staticmethod
    def test_with_remote(tmp_path):
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        actual = check_git_pullpush(tmp_path)
        assert actual == (True, True, "file:///.")

    @staticmethod
    def test_push_disabled(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        git_disable_push(tmp_path)
        actual = check_git_pullpush(tmp_path)
        assert actual == (True, False, None)

    @staticmethod
    @pytest.mark.parametrize("disabled_url", ["DISABLED", "NONE", "push-DISABLED-here"])
    def test_push_url_disabled_variants(tmp_path, disabled_url):
        """Various disabled URL patterns are detected."""
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        call_git("remote", "set-url", "--push", "origin", disabled_url, cwd=tmp_path)
        pull_possible, push_possible, push_url = check_git_pullpush(tmp_path)
        assert pull_possible is True
        assert push_possible is False
        assert push_url == disabled_url


class TestCallGit:
    @staticmethod
    def test_valid_command(tmp_path):
        git_init(tmp_path)
        result = call_git("status", cwd=tmp_path)
        assert result == 0

    @staticmethod
    def test_invalid_command(tmp_path):
        result = call_git("INVALIDCMD", cwd=tmp_path)
        assert result != 0
