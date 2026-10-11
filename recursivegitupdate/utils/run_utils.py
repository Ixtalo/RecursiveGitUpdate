"""Utility function to run commands on OS."""

import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from loguru import logger

__all__ = ["run_command"]

# Default timeout for subprocess commands (seconds)
DEFAULT_TIMEOUT: float = 60.0


def _print_std(text: str, stream: TextIO) -> None:
    text = text.strip()
    if text:
        print(text, file=stream)


def run_command(cmd: Sequence[str], cwd: Path, timeout: float = DEFAULT_TIMEOUT) -> int:
    """Run a command, wait till it finishes and capture its output.

    Args:
        cmd: The command and its arguments (no shell involved, no word splitting).
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait for the command to finish.

    Returns:
        The process return code. Returns -1 if the command was killed because of the timeout.

    Raises:
        FileNotFoundError: If the command binary does not exist.
    """
    cmd_str = shlex.join(cmd)
    logger.debug("running command: {} (cwd:{})", cmd_str, cwd.resolve())

    try:
        proc = subprocess.run(
            list(cmd),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Timeout ({:.1f}s) hit while running command: {}", timeout, cmd_str)
        return -1

    _print_std(proc.stdout, sys.stdout)
    if proc.returncode != 0:
        _print_std(proc.stderr, sys.stderr)

    return proc.returncode
