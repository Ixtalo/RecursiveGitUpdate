"""Scan a directory tree for version-controlled folders."""

import os
from pathlib import Path

from loguru import logger

from recursivegitupdate.models import FolderCandidates

__all__ = ["DIRS_TO_IGNORE", "IGNORE_FILE", "IGNORE_FILE_NOGITPUSH", "scan_for_folder_candidates"]

#: Place this file in a directory tree to recursively ignore the whole subtree.
IGNORE_FILE = ".recursive_rcs_update_ignore"
#: Place this file in a directory tree to recursively ignore git push for the subtree.
IGNORE_FILE_NOGITPUSH = ".recursive_rcs_update_no-git-push"
#: Folders to ignore during scanning (as frozenset for O(1) lookup).
DIRS_TO_IGNORE = frozenset((".metadata", ".vs", "build", "target"))


def scan_for_folder_candidates(root: Path) -> FolderCandidates:
    """Collect all relevant RCS folders starting from root.

    Repository roots end the descent. ``IGNORE_FILE_NOGITPUSH`` is inherited by the whole subtree.
    """
    git: list[Path] = []
    svn: list[Path] = []
    ignores: list[Path] = []
    git_nopush: list[Path] = []
    nopush_roots: list[Path] = []

    def log_scan_error(ex: OSError) -> None:
        logger.warning("Cannot scan directory: {}", ex)

    for dirpath, dirnames, filenames in os.walk(root, onerror=log_scan_error):
        folder = Path(dirpath)
        names = {*dirnames, *filenames}

        if IGNORE_FILE in names:
            logger.warning("Ignore file found, *recursively* ignoring {}", folder)
            ignores.append(folder)
            dirnames.clear()
            continue

        if IGNORE_FILE_NOGITPUSH in names:
            logger.warning("Ignore file found, *recursively* no git push for {}", folder)
            nopush_roots.append(folder)

        # '.git' may also be a file (worktrees, submodules).
        lower_names = {name.lower() for name in names}
        if ".git" in lower_names:
            git.append(folder)
            if any(folder.is_relative_to(nopush_root) for nopush_root in nopush_roots):
                git_nopush.append(folder)
        elif ".svn" in lower_names:
            svn.append(folder)
        else:
            # Prune in place: sorted for deterministic order, os.walk never follows symlinked dirs.
            dirnames[:] = sorted(name for name in dirnames if name not in DIRS_TO_IGNORE)
            continue

        dirnames.clear()  # repository root: do not descend any further

    return FolderCandidates(git=git, svn=svn, ignores=ignores, git_nopush=git_nopush)
