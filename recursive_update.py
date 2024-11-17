#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Calls main() method."""
import os
# noqa: D100,D104

import sys
import runpy
from pathlib import Path


def activate_virtualenv():
    """Activates the virtualenv, if needed."""
    # check if already in a virtualenv
    if os.environ.get("VIRTUAL_ENV"):
        # already ok
        return
    # resolve symlink to this file and produce virtualenv path
    venv_path = Path(__file__).readlink().parent.joinpath('.venv')
    # path to the activation script (activate_this.py can be used by native interpreter)
    activate_this = venv_path.joinpath('bin', 'activate_this.py')
    # make sure it actually exists
    if activate_this.is_file():
        # Execute code located at the specified filesystem location
        runpy.run_path(str(activate_this.resolve()))


if __name__ == "__main__":
    activate_virtualenv()
    from recursivegitupdate.recursive_update import main
    sys.exit(main())
