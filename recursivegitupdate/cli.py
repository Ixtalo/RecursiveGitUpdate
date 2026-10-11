"""Command line interface of recursive-git-update."""

import os
import shlex
import sys
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from recursivegitupdate import __version__
from recursivegitupdate.recursive_update import run

__all__ = ["app"]

_LOG_FORMAT = "<level>{time:YYYY-MM-DD HH:mm:ss} {level: <8} {message}</level>"

app = typer.Typer(
    add_completion=False,
    pretty_exceptions_show_locals=False,
    epilog=r"Putty SSH agent on MS Windows and TortoiseGit: "
    r"set GIT_SSH=c:\Program Files\TortoiseGit\bin\TortoisePlink.exe",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"Recursive RCS Updater {__version__}")
        raise typer.Exit


def _setup_logging(verbose: bool) -> None:
    """Replace loguru's default stderr sink by a level-colored stdout sink."""
    logger.remove()
    logger.add(sys.stdout, level="DEBUG" if verbose else "INFO", format=_LOG_FORMAT)


@app.command(no_args_is_help=True)
def main(
    basepath: Annotated[
        Path,
        typer.Argument(
            exists=True, file_okay=False, metavar="BASEPATH", help="Starting path for recursive folder scan."
        ),
    ],
    cache_max_age: Annotated[
        float, typer.Option(min=0, help="Maximum age for the cache in N days (could be float).")
    ] = 1.0,
    git_push: Annotated[
        bool, typer.Option("--git-push", help="Allow pushing for git (default is only to pull).")
    ] = False,
    git_args: Annotated[
        str, typer.Option("--git-args", help="Additional arguments appended to git pull command.")
    ] = "",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be done without actually executing commands.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Be verbose.")] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    """Recursively find Git/SVN folders below BASEPATH and update them.

    Git: git pull (and git push with --git-push). SVN: svn up.
    """
    try:
        extra_args = tuple(shlex.split(git_args))
    except ValueError as ex:
        raise typer.BadParameter(str(ex), param_hint="'--git-args'") from ex

    # DEBUG environment variable is a shortcut for --verbose
    verbose = verbose or os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    _setup_logging(verbose)

    basepath = basepath.absolute()
    logger.debug("basepath: {}", basepath.resolve())

    returncode = run(basepath, cache_max_age, git_push, dry_run=dry_run, extra_args=extra_args)
    raise typer.Exit(returncode)
