"""Recursively find SVN or GIT folders and update them.

Commands:
    Git: 1. git pull, 2. git push
    SVN: svn up
"""

import shlex
from collections.abc import Collection, Iterator, Sequence
from pathlib import Path
from subprocess import SubprocessError

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from recursivegitupdate.foldercandidatescache import FolderCandidatesCache
from recursivegitupdate.models import CacheData, FolderCandidates, Results
from recursivegitupdate.scanner import scan_for_folder_candidates
from recursivegitupdate.utils.git_utils import call_git, check_git_pullpush
from recursivegitupdate.utils.run_utils import run_command

__all__ = ["run", "setup_cache"]

_DRY_RUN_PREFIX = "[DRY-RUN]"


# ============================================================
# Cache
# ============================================================


def setup_cache(basepath: Path, cache_max_age: float) -> tuple[FolderCandidatesCache, FolderCandidates]:
    """Set up the folder candidates cache, i.e., create new or load from cache."""
    cache = FolderCandidatesCache.for_basepath(basepath, outdated_age_max_days=cache_max_age)

    data = cache.load()
    if data is not None and data.root.resolve() != basepath.resolve():  # e.g., hash collision
        logger.warning("Cache file belongs to '{}' - ignoring it.", data.root)
        data = None

    if data is None:
        logger.warning("No cache file found or cache is outdated! Updating cache ...")
        logger.info("Scanning for all folder candidates ...")
        candidates = scan_for_folder_candidates(basepath)
        cache.update(CacheData(root=basepath, candidates=candidates))
        return cache, candidates

    logger.info("Using cache, file {}", cache.cache_filepath.resolve())
    return cache, data.candidates


# ============================================================
# Git operations
# ============================================================


def _existing_folders(kind: str, folders: Sequence[Path], cache: FolderCandidatesCache) -> Iterator[Path]:
    """Yield the folders that still exist and log the progress.

    Folders which vanished since the cache was written invalidate the cache.
    """
    if not folders:
        return

    n_dirs = len(folders)
    logger.info("Processing {} {} directories ...", n_dirs, kind)

    for i, folder in enumerate(folders, start=1):
        if not folder.is_dir():
            logger.warning("Directory doesn't exist (anymore): {}", folder)
            cache.invalidate()
            continue

        logger.info("({}/{}) Updating {} repository '{}' ...", i, n_dirs, kind, folder.resolve())
        yield folder


def _do_git_pull(folder: Path, dry_run: bool, extra_args: Sequence[str] = ()) -> tuple[bool, str]:
    """Execute git pull for a single repository.

    Args:
        folder: The git working directory.
        dry_run: If True, only log what would be done.
        extra_args: Additional arguments appended to the git pull command.

    Returns:
        Tuple of (success: bool, message: str).
    """
    args = ["pull", "--recurse-submodules", "--all", *extra_args]

    if dry_run:
        logger.info("{} Would run: git {} (in {})", _DRY_RUN_PREFIX, shlex.join(args), folder.resolve())
        return True, "git pull OK (dry-run)"

    returncode = call_git(*args, cwd=folder)
    if returncode != 0:
        msg = f"git pull error! (return code: {returncode:d})"
        logger.error(msg)
        return False, msg

    return True, "git pull OK"


def _do_git_push(folder: Path, dry_run: bool) -> tuple[bool, str]:
    """Execute git push for a single repository.

    Returns:
        Tuple of (success: bool, message: str).
    """
    if dry_run:
        logger.info("{} Would run: git push --all (in {})", _DRY_RUN_PREFIX, folder.resolve())
        return True, "git pull + push OK (dry-run)"

    returncode = call_git("push", "--all", cwd=folder)
    if returncode != 0:
        msg = f"git push error! (return code: {returncode:d})"
        logger.error(msg)
        return False, msg

    return True, "git pull + push OK"


def _should_skip_push(push_url: str | None) -> bool:
    """Determine whether push should be skipped for a given remote URL."""
    if not push_url:
        return True
    if "github.com" in push_url:
        logger.warning("Not running 'git push' for this github.com repository.")
        return True
    return False


def _update_git(
    folder: Path,
    git_do_push: bool,
    *,
    dry_run: bool,
    extra_args: Sequence[str],
    nopush: Collection[Path],
) -> tuple[bool, str]:
    """Pull (and optionally push) a single git repository.

    Returns:
        Tuple of (success: bool, message: str) describing the final outcome.
    """
    # Check what's actually possible (read-only operation)
    try:
        git_pull_possible, git_push_possible, push_url = check_git_pullpush(folder)
    except (SubprocessError, OSError) as ex:  # includes CalledProcessError and TimeoutExpired
        logger.error("Failed to query git remotes for '{}': {}", folder.resolve(), ex)
        return False, f"git remote check failed: {ex}"

    if not git_pull_possible:
        logger.warning("No git pull possible - skipping ...")
        return False, "no git pull possible"

    pull_ok, msg = _do_git_pull(folder, dry_run, extra_args)

    # git push only if enabled, possible, and not skipped
    if not (pull_ok and git_do_push and git_push_possible):
        return pull_ok, msg
    if folder in nopush:
        logger.info("Not running 'git push' (no-git-push marker file in tree): {}", folder)
        return True, msg
    if _should_skip_push(push_url):
        return True, msg

    return _do_git_push(folder, dry_run)


def _process_git(
    folders: Sequence[Path],
    cache: FolderCandidatesCache,
    results: Results,
    git_do_push: bool,
    *,
    dry_run: bool = False,
    extra_args: Sequence[str] = (),
    nopush: Collection[Path] = (),
) -> None:
    """Pull (and optionally push) all git repositories.

    Repositories listed in ``nopush`` are only pulled, never pushed.
    """
    for folder in _existing_folders("git", folders, cache):
        ok, msg = _update_git(folder, git_do_push, dry_run=dry_run, extra_args=extra_args, nopush=nopush)
        (results.ok if ok else results.error)[folder] = msg


# ============================================================
# SVN operations
# ============================================================


def _process_svn(
    folders: Sequence[Path], cache: FolderCandidatesCache, results: Results, *, dry_run: bool = False
) -> None:
    """Update all svn repositories."""
    for folder in _existing_folders("svn", folders, cache):
        if dry_run:
            logger.info("{} Would run: svn up (in {})", _DRY_RUN_PREFIX, folder.resolve())
            results.ok[folder] = "svn OK (dry-run)"
            continue

        returncode = run_command(["svn", "up"], folder)
        if returncode != 0:
            logger.debug("An error occurred while svn up! returncode: {}", returncode)
            results.error[folder] = f"svn ERROR! returncode:{returncode:d}"
        else:
            results.ok[folder] = "svn OK"


# ============================================================
# Output / Overview
# ============================================================


console = Console()

#: Rich color per result category, used for table styling and the final summary.
_CATEGORY_STYLES = {"ignored": "yellow", "OK": "green", "errors": "red"}


def _show_overview_category(name: str, data: dict[Path, str]) -> None:
    """Render a colored overview table for a single result category."""
    if not data:
        return

    style = _CATEGORY_STYLES.get(name, "white")
    table = Table(
        title=f"{name} ({len(data)})",
        title_style=f"bold {style}",
        header_style=f"bold {style}",
        border_style=style,
        expand=True,
    )
    table.add_column("Folder", overflow="fold", ratio=2)
    table.add_column("Message", overflow="fold", ratio=3)
    for folder, resmsg in data.items():
        table.add_row(str(folder), resmsg)
    console.print(table)


# ============================================================
# Main entry point
# ============================================================


def run(
    basepath: Path,
    cache_max_age: float,
    git_do_push: bool,
    *,
    dry_run: bool = False,
    extra_args: Sequence[str] = (),
) -> int:
    """Run the program's main part.

    Returns:
        0 on success, 1 if any repository update failed.
    """
    if dry_run:
        logger.info("{} Dry-run mode enabled. No changes will be made.", _DRY_RUN_PREFIX)

    cache, candidates = setup_cache(basepath, cache_max_age)
    results = Results()

    # Perform pull/push/update actions
    _process_git(
        candidates.git,
        cache,
        results,
        git_do_push,
        dry_run=dry_run,
        extra_args=extra_args,
        nopush=frozenset(candidates.git_nopush),
    )
    _process_svn(candidates.svn, cache, results, dry_run=dry_run)

    console.rule("[bold]All done[/bold]")

    # Convert ignores for overview presentation
    results.ignored.update(dict.fromkeys(candidates.ignores, "ignored"))

    # Present output
    _show_overview_category("ignored", results.ignored)
    _show_overview_category("OK", results.ok)
    _show_overview_category("errors", results.error)

    n_ok = len(results.ok)
    n_ig = len(results.ignored)
    n_er = len(results.error)

    summary_style = "bold red" if n_er else ("bold yellow" if n_ig else "bold green")
    console.print(
        Panel(
            f"[green]{n_ok} OK[/green], [yellow]{n_ig} ignored[/yellow], [red]{n_er} errors[/red]",
            border_style=summary_style,
        )
    )

    return 1 if results.has_errors else 0
