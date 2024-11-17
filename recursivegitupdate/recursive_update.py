#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""recursive_rcs_update.py - Recursively find SVN or GIT folders and update them.

Find folders which are managed by Revision-/Version-Control-System (RCS/VCS)
tools, e.g., Git or Subversion (SVN), and update them.

Commands:
    Git: 1. git pull, 2. git push
    SVN: svn up

Putty SSH agent on MS Windows and TortoiseGit:
`set GIT_SSH=c:\Program Files\TortoiseGit\bin\TortoisePlink.exe`

Usage:
  recursive_update.py [-v] [--cache-max-age n] [--git-push] [--args=..] <basepath>
  recursive_update.py -h | --help
  recursive_update.py --version

Arguments:
  <basepath>            Starting path for recursive folder scan.

Options:
  --args=ARGS           Additional git command arguments.
  --cache-max-age n     Maximum age for the cache in n days (could be float) [default: 1]
  --git-push            Allow pushing for git (default is only to pull)
  -v --verbose          Be verbose.
  -h --help             Show this screen.
  --version             Show version.
"""
# LICENSE:
#
# Copyright (C) 2015-2024 Ixtalo, ixtalo@gmail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import logging
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from docopt import docopt

from recursivegitupdate.foldercandidatescache import FolderCandidatesCache, CacheData
from recursivegitupdate.utils.git_utils import check_git_pullpush
from recursivegitupdate.utils.mylogging import setup_logging
from recursivegitupdate.utils.run_utils import run_command

__version__ = "1.13.0"
__date__ = "2015-06-05"
__updated__ = "2024-11-17"
__author__ = "Ixtalo"
__license__ = "AGPL-3.0+"
__email__ = "ixtalo@gmail.com"
__status__ = "Production"

"""Place this file in a directory tree to recursively ignore the whole subtree."""
IGNORE_FILE = ".recursive_rcs_update_ignore"
"""Place this file in a directory tree to recursively ignore git push for the subtree."""
IGNORE_FILE_NOGITPUSH = ".recursive_rcs_update_no-git-push"
"""The RCS meta-directories (e.g., .git, .svn)."""
RCS_DIR_NAMES = ('.git', '.svn')
# folders to ignore
DIRS_TO_IGNORE = ('.metadata', '.vs', 'build', 'target')
# debug switch
DEBUG = bool(os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"))


# pylint: disable=line-too-long


@dataclass(frozen=True)
class FolderCandidates:
    """Lists of RCS (git, svn) folder candidates."""

    git: List[Path]
    svn: List[Path]
    ignores: List[Path]


def scan_for_folder_candidates(root: Path) -> FolderCandidates:
    """Collect all relevant folders."""
    candidates = FolderCandidates([], [], [])
    __scan_for_folder_candidates_recursive(candidates, root)
    return candidates


def __scan_for_folder_candidates_recursive(candidates, root: Path):
    if not root.is_dir():
        # return and stop recursion here
        return
    entries = os.listdir(root)
    if IGNORE_FILE in entries:
        logging.warning("Ignore file found, *recursively* ignoring %s", root)
        candidates.ignores.append(root)
        # return and stop recursion here
        return
    if IGNORE_FILE_NOGITPUSH in entries:
        logging.warning("Ignore file found, *recursively* no git push for %s", root)
        # return and stop recursion here
        return
    # have a look on every item in the directory
    for filename in sorted(entries):
        filepath = root.joinpath(filename)
        if filepath.is_dir():
            dirname = filename  # just for clarification
            if dirname in DIRS_TO_IGNORE:
                # skip ignored directories - the whole subtree will be ignored!
                continue
            if dirname.lower() == '.git':
                candidates.git.append(root)
                return
            if dirname.lower() == '.svn':
                candidates.svn.append(root)
                return

            # recursive processing of child folders
            __scan_for_folder_candidates_recursive(candidates, filepath)


def setup_cache(basepath: Path, cache_max_age: float) -> Tuple[FolderCandidatesCache, FolderCandidates]:
    """Set up the folder candidates cache, i.e., create new or load from cache."""
    # cache
    cachefile = basepath.joinpath(FolderCandidatesCache.CACHE_FILE)
    cache = FolderCandidatesCache(cachefile, outdated_age_max_days=cache_max_age)
    data = cache.load()
    if not data:
        logging.warning("No cache file found or cache is outdated! Updating cache ...")
        logging.info("Scanning for all folder candidates ...")
        candidates = scan_for_folder_candidates(basepath)
        data = CacheData(basepath, candidates)
        cache.update(data)
    else:
        if data.root == basepath:
            logging.info("Using cache, file %s", cachefile.resolve())
            # convert
            candidates = FolderCandidates(
                git=data.candidates.get("git", []),
                svn=data.candidates.get("svn", []),
                ignores=data.candidates.get("ignores", [])
            )
        else:
            raise RuntimeWarning(f"Current cache file is not valid for given basepath! "
                                 f"Actually it is for '{data.root.resolve()}'. Remove file manually to continue!")
    assert isinstance(candidates, FolderCandidates)
    return cache, candidates


def run(basepath: Path, cache_max_age, git_do_push):
    """Run the programs main part."""
    cache, candidates = setup_cache(basepath, cache_max_age)

    @dataclass(frozen=True)
    class Results:
        """Result messages for each category."""

        ok = OrderedDict()
        error = OrderedDict()
        ignored = OrderedDict()

    results = Results()

    def run_git(folders):
        if not folders:
            return
        n_dirs = len(folders)
        logging.info("Processing %d git directories ...", n_dirs)
        for i, folder in enumerate(folders):
            if not folder.is_dir():
                logging.warning("Directory doesn't exist (anymore): %s", folder)
                cache.invalidate()
                continue

            logging.info("(%d/%d) Updating git repository '%s' ...",
                         i + 1, n_dirs, folder.resolve())

            # first check what's actually possible
            git_pull_possible, git_push_possible, push_url = check_git_pullpush(folder)
            if not git_pull_possible:
                logging.warning("No git pull possible - skipping ...")
                results.error[folder] = "no git pull possible"
                continue

            # git pull
            returncode_pull = run_command(folder, "git pull --recurse-submodules --all")
            if returncode_pull == 0:
                results.ok[folder] = "git pull OK"
            else:
                errmsg = f"git pull error! (return code: {returncode_pull:d})"
                logging.error(errmsg)
                results.error[folder] = errmsg
                # abort here
                continue

            # check if git pushing is enabled via CLI parameter and actually possible
            if git_do_push and git_push_possible:
                # check if this is a github.com remote repository
                if 'github.com' in push_url:
                    # ignoring www.github.com repositories
                    logging.warning("Not running 'git push' for this github.com repository.")
                else:
                    returncode_push = run_command(folder, "git push --all")
                    if returncode_push == 0:
                        results.ok[folder] = "git pull + push OK"
                    else:
                        errmsg = f"git push error! (return code: {returncode_pull:d})"
                        logging.error(errmsg)
                        results.error[folder] = errmsg
                        results.ok[folder] = "git pull OK, push ERROR"

    def run_svn(folders):
        if not folders:
            return
        n_dirs = len(folders)
        logging.info("Processing %d svn directories ...", n_dirs)
        for i, folder in enumerate(folders):
            if not folder.is_dir():
                logging.warning("Directory doesn't exist anymore: %s", folder)
                cache.invalidate()
            else:
                logging.info("(%d/%d) Updating svn repository '%s' ...", i + 1, n_dirs, folder)
                returncode = run_command(folder, "svn up")
                if returncode != 0:
                    logging.debug("An erroroccured while svn up! returncode: %d", returncode)
                    results.error[folder] = f"svn ERROR! returncode:{returncode:d}"
                else:
                    results.ok[folder] = "svn OK"

    def show_overview_category(name: str, log_level: int, results: dict):
        overview = ""
        for folder, resmsg in results.items():
            overview += f"{folder}\t{resmsg}\n"
        if overview:
            logging.log(log_level, "overview for %s:\n%s", name, overview.strip())

    # do the git-pull/svn-up action
    run_git(getattr(candidates, "git"))
    run_svn(getattr(candidates, "svn"))

    logging.info("All done.\n" + "-" * 60 + "\n")   # pylint: disable=logging-not-lazy

    # convert ignores for overview presentation
    for entry in candidates.ignores:
        results.ignored[entry] = "ignored"

    # present output
    show_overview_category("ignored", logging.WARNING, results.ignored)
    show_overview_category("OK", logging.INFO, results.ok)
    show_overview_category("errors", logging.ERROR, results.error)
    n_ok = len(results.ok)
    n_ig = len(results.ignored)
    n_er = len(results.error)
    if n_er:
        level = logging.ERROR
    elif n_ig:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.log(level, "%d OK, %d ignored, %d errors", n_ok, n_ig, n_er)

    return 0


def main():
    """Run the program's main method."""
    arguments = docopt(__doc__, version=f"Recursive RCS Updater {__version__}")
    # print(arguments)

    # CLI argument handling
    arg_basepath = os.path.abspath(arguments["<basepath>"])
    arg_verbose = arguments["--verbose"]
    arg_cache_max_age = float(arguments["--cache-max-age"])
    arg_git_do_push = bool(arguments["--git-push"])
    if DEBUG:
        # force reinitialization
        arg_cache_max_age = 0

    # setup logging
    setup_logging(level=logging.DEBUG if arg_verbose else logging.INFO)

    basepath = Path(arg_basepath)
    logging.debug("basepath: %s", basepath.resolve())

    return run(basepath, arg_cache_max_age, arg_git_do_push)


if __name__ == '__main__':
    if DEBUG:
        sys.argv.append('--verbose')
    if os.environ.get("PROFILE", "").lower() in ("true", "1", "yes"):
        import cProfile
        import pstats
        profile_filename = f"{__file__}.profile"    # pylint: disable=invalid-name
        cProfile.run("main()", profile_filename)
        with open(f"{profile_filename}.txt", "w", encoding="utf8") as statsfp:
            profile_stats = pstats.Stats(profile_filename, stream=statsfp)
            stats = profile_stats.strip_dirs().sort_stats("cumulative")
            stats.print_stats()
        sys.exit(0)
    sys.exit(main())
