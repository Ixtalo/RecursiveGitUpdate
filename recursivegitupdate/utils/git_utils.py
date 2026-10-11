"""Utilities for GIT."""

import shutil
from functools import cache
from pathlib import Path
from subprocess import TimeoutExpired, check_output

from loguru import logger

from recursivegitupdate.utils.run_utils import run_command

__all__ = ["call_git", "check_git_pullpush", "extract_origin_push_url", "get_git_cmd"]

# Timeout for git remote queries (seconds)
_GIT_REMOTE_TIMEOUT: float = 30.0


@cache
def get_git_cmd() -> str:
    """Return the path to the git binary (cached after first successful lookup).

    Raises:
        FileNotFoundError: If git is not found in PATH.
    """
    git_cmd = shutil.which("git")
    if not git_cmd:
        raise FileNotFoundError(
            "git executable not found in PATH. Please install git or ensure it is on the system PATH."
        )
    return git_cmd


def call_git(*arguments: str, cwd: Path) -> int:
    """Run the OS git command with given arguments and inside specified working directory."""
    return run_command([get_git_cmd(), *arguments], cwd)


def extract_origin_push_url(remote_output: str) -> str | None:
    """Extract the git origin remote push URL from `git remote -v` output."""
    for line in remote_output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "origin" and parts[2] == "(push)":
            return parts[1]
    return None


def check_git_pullpush(cwd: Path) -> tuple[bool, bool, str | None]:
    """Check if pull and push are possible because remote origins are actually set.

    Returns:
        Tuple of (pull_possible, push_possible, push_url).
        push_url may be None if no origin push remote is configured.

    Raises:
        subprocess.CalledProcessError: If git command fails.
        subprocess.TimeoutExpired: If git command hangs.
    """
    cmd = [get_git_cmd(), "remote", "--verbose"]
    logger.debug("running command: {} (cwd:{})", cmd, cwd.resolve())

    try:
        stdout = check_output(cmd, cwd=cwd, encoding="utf8", timeout=_GIT_REMOTE_TIMEOUT)
    except TimeoutExpired:
        logger.error("Timeout querying git remotes in '{}'", cwd.resolve())
        raise

    # if no remotes are set then stdout is empty
    git_pull_possible = " (fetch)" in stdout

    # additional detail check of push URLs, i.e., check if deactivated
    push_url = extract_origin_push_url(stdout)
    logger.debug("push_url: {}", push_url)

    # push deactivated if empty or has certain values
    git_push_possible = push_url is not None and "DISABLED" not in push_url and "NONE" not in push_url

    return git_pull_possible, git_push_possible, push_url
