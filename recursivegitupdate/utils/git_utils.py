# -*- coding: utf-8 -*-
"""Utilities for GIT."""
import logging
import shlex
from pathlib import Path
from subprocess import Popen, PIPE
from typing import Tuple


def extract_origin_push_url(remote_output: str) -> str | None:
    """Extract the git origin remote URL from `git remote -v` output."""
    for line in remote_output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "origin" and parts[2] == "(push)":
            return parts[1]
    return None


def check_git_pullpush(root: Path) -> Tuple[bool, bool, str]:
    """Check if pull and push are possible because remote origins are actually set."""
    # -n do not query remotes
    cmd = "git remote -v show -n"
    logging.debug("running command: %s (cwd:%s)", cmd, root.resolve())
    with Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE, cwd=root) as proc:
        stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf8"))

    stdout = stdout.decode("utf8")

    # if no remotes are set then stdout is empty
    # otherwise, example:
    # origin	ssh://git@hostname/RecursiveGitUpdate.git (fetch)
    # origin	ssh://git@hostname/RecursiveGitUpdate.git (push)
    # foobar	file://. (fetch)
    # foobar	file://. (push)
    # foobarbla	file://. (fetch)
    # foobarbla	file://. (push)
    git_pull_possible = ' (fetch)' in stdout

    # additional detail check of push URLs, i.e., check if deactivated
    push_url = extract_origin_push_url(stdout)
    logging.debug("push_url: %s", push_url)
    # push deactivated if empty or has certain values
    git_push_possible = push_url is not None and 'DISABLED' not in push_url and 'NONE' not in push_url

    return git_pull_possible, git_push_possible, push_url
