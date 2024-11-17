# -*- coding: utf-8 -*-
"""Unit tests."""
import logging

import pytest

from recursivegitupdate.utils.run_utils import run_command

# pylint: disable=missing-function-docstring,missing-class-docstring


def test_run_system_command_nosuchfile(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_command(tmp_path, "NOSUCHCOMMANDfooo123")


def test_run_system_command_git(tmp_path, capsys):
    # action
    actual = run_command(tmp_path, "git status")
    # check
    assert actual == 128
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert stderr == 'fatal: not a git repository (or any of the parent directories): .git\n'


def test_run_system_command_ls(tmp_path, capsys):
    # action
    actual = run_command(tmp_path, "/usr/bin/ls --all")
    # check
    assert actual == 0
    stdout, stderr = capsys.readouterr()
    assert stdout == '.\n..\n'
    assert stderr == ""


def test_run_system_command_timeout(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    # action
    actual = run_command(tmp_path, "sleep 10", timeout=0.1)
    # check
    assert actual == -9
    assert caplog.messages[0] == f"running command: sleep 10 (cwd:{tmp_path.resolve()})"
    assert caplog.messages[1] == 'Timeout hit while running command sleep 10'
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert stderr == ""
