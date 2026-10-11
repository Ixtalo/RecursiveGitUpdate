"""Unit tests for run_utils module."""

import logging
import shutil

import pytest

from recursivegitupdate.utils.git_utils import call_git
from recursivegitupdate.utils.run_utils import run_command

# Skip tests that depend on specific Unix binaries
_has_ls = shutil.which("ls") is not None


def test_run_system_command_nosuchfile(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_command(["NOSUCHCOMMANDfooo123"], tmp_path)


def test_run_system_command_git(tmp_path, capsys):
    # action
    actual = call_git("status", cwd=tmp_path)
    # check
    assert actual == 128
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert "fatal: not a git repository" in stderr


@pytest.mark.skipif(not _has_ls, reason="ls not available")
def test_run_system_command_ls(tmp_path, capsys):
    ls_path = shutil.which("ls")
    # action
    actual = run_command([ls_path, "--all"], tmp_path)
    # check
    assert actual == 0
    stdout, _ = capsys.readouterr()
    assert "." in stdout
    assert ".." in stdout


def test_run_system_command_timeout(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    # action
    actual = run_command(["sleep", "10"], tmp_path, timeout=0.1)
    # check — killed process has negative return code
    assert actual != 0
    assert any("Timeout" in msg for msg in caplog.messages)


@pytest.mark.skipif(not _has_ls, reason="ls not available")
def test_run_system_command_returncode(tmp_path, capsys):
    """Non-zero exit code is returned and stderr is printed."""
    ls_path = shutil.which("ls")
    actual = run_command([ls_path, "/DOESNOTEXIST_XYZ"], tmp_path)
    assert actual != 0
    _, stderr = capsys.readouterr()
    assert stderr  # some error message present
