# -*- coding: utf-8 -*-
"""Unit tests."""
import logging
import shlex
import subprocess

import pytest

from recursivegitupdate.utils.git_utils import extract_origin_push_url, check_git_pullpush

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
        with pytest.raises(RuntimeError) as ex:
            check_git_pullpush(tmp_path)
        assert str(ex) == ("<ExceptionInfo RuntimeError('fatal: not a git repository (or any of the "
                           "parent directories): .git\\n') tblen=2>")

    @staticmethod
    def test_check_git_pullpush_gitdir__noremote(tmp_path):
        # prepare
        subprocess.call(shlex.split("git init"), cwd=tmp_path)
        # action
        actual = check_git_pullpush(tmp_path)
        # check
        assert actual == (False, False, None)

    @staticmethod
    def test_check_git_pullpush__gitdir_withremote(tmp_path):
        # prepare
        subprocess.call(shlex.split("git init"), cwd=tmp_path)
        subprocess.call(shlex.split("git remote add origin file://."), cwd=tmp_path)
        # action
        actual = check_git_pullpush(tmp_path)
        # check
        assert actual == (True, True, 'file://.')

    @staticmethod
    def test_check_git_pullpush__gitdir_nopush(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        # prepare
        subprocess.call(shlex.split("git init"), cwd=tmp_path)
        subprocess.call(shlex.split("git remote add origin file://."), cwd=tmp_path)
        # disable push
        subprocess.call(shlex.split("git remote set-url --push origin ''"), cwd=tmp_path)
        # action
        actual = check_git_pullpush(tmp_path)
        # check
        assert actual == (True, False, None)
        assert caplog.messages[0] == f"running command: git remote -v show -n (cwd:{tmp_path.resolve()})"
        assert caplog.messages[1] == 'push_url: None'
