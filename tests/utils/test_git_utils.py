# -*- coding: utf-8 -*-
"""Unit tests."""
import logging
from subprocess import CalledProcessError

import pytest

from recursivegitupdate.utils.git_utils import extract_origin_push_url, check_git_pullpush
from tests.utilities import git_add_remote, git_init, git_disable_push


# pylint: disable=missing-function-docstring,missing-class-docstring


class TestExtractOriginPushUrl:

    @staticmethod
    def test_extract_origin_push_url():
        assert not extract_origin_push_url("")
        assert not extract_origin_push_url("foobar")
        assert extract_origin_push_url("origin bla (push)") == "bla"
        assert extract_origin_push_url("origin bla (push)\norigin2 foo (push)") == "bla"
        # 2 'origin'
        assert extract_origin_push_url("origin bla (push)\norigin foo (push)") == "bla"


class TestCheckGitPullPush:

    @staticmethod
    def test_check_git_pullpush__nogitdir(tmp_path):
        with pytest.raises(CalledProcessError) as ex:
            check_git_pullpush(tmp_path)
        assert str(ex) == ("<ExceptionInfo CalledProcessError(128, "
                           "['/usr/bin/git', 'remote', '--verbose']) tblen=4>")

    @staticmethod
    def test_check_git_pullpush_gitdir__noremote(tmp_path):
        # prepare
        git_init(tmp_path)
        # action
        actual = check_git_pullpush(tmp_path)
        # check
        assert actual == (False, False, None)

    @staticmethod
    def test_check_git_pullpush__gitdir_withremote(tmp_path):
        # prepare
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        # action
        actual = check_git_pullpush(tmp_path)
        # check
        assert actual == (True, True, "file:///.")

    @staticmethod
    def test_check_git_pullpush__gitdir_nopush(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        # prepare
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        git_disable_push(tmp_path)
        # action
        actual = check_git_pullpush(tmp_path)
        # check
        # (git_pull_possible, git_push_possible, push_url)
        assert actual == (True, False, None)
        assert (caplog.messages[0] == f"running command: /usr/bin/git "
                f"init --initial-branch main (cwd:{tmp_path.resolve()})")
        assert (caplog.messages[1] == f"running command: /usr/bin/git "
                f"remote add origin file:///. (cwd:{tmp_path.resolve()})")
        assert (caplog.messages[2] == f"running command: /usr/bin/git "
                f"remote set-url --push origin ' ' (cwd:{tmp_path.resolve()})")
        assert (caplog.messages[3] == f"running command: /usr/bin/git "
                f"remote --verbose (cwd:{tmp_path.resolve()})")
        assert caplog.messages[4] == 'push_url: None'
        assert len(caplog.messages) == 5
