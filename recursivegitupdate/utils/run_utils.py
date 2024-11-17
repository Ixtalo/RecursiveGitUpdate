# -*- coding: utf-8 -*-
"""Utility function to run commands on OS."""
import logging
import shlex
import sys
from pathlib import Path
from subprocess import Popen, TimeoutExpired, PIPE


def run_command(workingdir: Path, cmd: str, timeout=30):
    """Run a command, wait till it finishes and capture its output."""
    def print_std(data, stream=sys.stdout):
        if data:
            print(data.decode("utf8").strip(), file=stream)

    logging.debug("running command: %s (cwd:%s)", cmd, workingdir.resolve())
    with Popen(shlex.split(cmd), cwd=workingdir, stdout=PIPE, stderr=PIPE) as proc:
        stderr = None
        try:
            # Read data from stdout and stderr, until end-of-file is reached.
            # Wait for process to terminate.
            stdout, stderr = proc.communicate(timeout=timeout)
            print_std(stdout)
        except TimeoutExpired:
            logging.warning("Timeout hit while running command %s", cmd)
            proc.kill()
            stdout, stderr = proc.communicate()
            print_std(stdout)
        except Exception as ex:
            logging.exception(ex)
    return_code = proc.returncode
    if return_code != 0:
        print_std(stderr, stream=sys.stderr)
    return return_code
