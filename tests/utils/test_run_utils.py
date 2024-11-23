# -*- coding: utf-8 -*-
"""Unit tests."""
import logging

import pytest

from recursivegitupdate.utils.run_utils import run_command
from recursivegitupdate.utils.git_utils import call_git


# pylint: disable=missing-function-docstring,missing-class-docstring


def test_run_system_command_nosuchfile(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_command("NOSUCHCOMMANDfooo123", tmp_path)


def test_run_system_command_git(tmp_path, capsys):
    # action
    actual = call_git("status", tmp_path)
    # check
    assert actual == 128
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert stderr == 'fatal: not a git repository (or any of the parent directories): .git\n'


def test_run_system_command_ls(tmp_path, capsys):
    # action
    actual = run_command("/usr/bin/ls --all", tmp_path)
    # check
    assert actual == 0
    stdout, stderr = capsys.readouterr()
    assert stdout == '.\n..\n'
    assert stderr == ""


def test_run_system_command_timeout(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    # action
    actual = run_command("sleep 10", tmp_path, timeout=0.1)
    # check
    assert actual == -9
    assert caplog.messages[0] == f"running command: sleep 10 (cwd:{tmp_path.resolve()})"
    assert caplog.messages[1] == 'Timeout hit while running command sleep 10'
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert stderr == ""
