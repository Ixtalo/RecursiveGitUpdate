#!/usr/bin/env python3
"""Calls the CLI app with optional virtualenv activation."""

import os
import runpy
from pathlib import Path


def activate_virtualenv() -> None:
    """Activate the virtualenv, if needed and available."""
    # check if already in a virtualenv
    if os.environ.get("VIRTUAL_ENV"):
        return

    # Resolve this script's actual location (follow symlinks if applicable)
    script_path = Path(__file__)
    try:
        script_path = script_path.resolve(strict=True)
    except OSError:
        # resolve() failed (broken symlink, permission error, etc.)
        return

    venv_path = script_path.parent / ".venv"
    activate_this = venv_path / "bin" / "activate_this.py"

    if activate_this.is_file():
        runpy.run_path(str(activate_this))


if __name__ == "__main__":
    activate_virtualenv()
    from recursivegitupdate.cli import app

    app()
