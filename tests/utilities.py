# -*- coding: utf-8 -*-
"""Utility functions for unit tests."""
from pathlib import Path

from recursivegitupdate.utils.git_utils import call_git


def git_init(cwd: Path) -> int:
    """Run git init."""
    return call_git("init --initial-branch main", cwd=cwd)


def git_add_remote(cwd: Path, remote: str) -> int:
    """Run git remove add origin."""
    return call_git(f"remote add origin {remote}", cwd=cwd)


def git_disable_push(cwd: Path) -> int:
    """Disable the git-push-url."""
    # NOTE: git 2.47 does not work with an empty '', it needs ' ' (a space)
    return call_git("remote set-url --push origin ' '", cwd=cwd)
