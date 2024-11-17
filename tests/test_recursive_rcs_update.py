# -*- coding: utf-8 -*-
"""Unit tests."""
import logging
import shlex
import subprocess
import sys
from pathlib import Path

from recursivegitupdate.recursive_update import (
    scan_for_folder_candidates,
    FolderCandidates,
    IGNORE_FILE,
    IGNORE_FILE_NOGITPUSH,
    DIRS_TO_IGNORE,
    setup_cache,
    main
)
from recursivegitupdate.foldercandidatescache import FolderCandidatesCache


# pylint: disable=missing-function-docstring,missing-class-docstring


class TestScanFolderCandidates:

    @staticmethod
    def test_scan_for_folder_candidates_empty(tmp_path):
        actual = scan_for_folder_candidates(tmp_path)
        assert actual == FolderCandidates(git=[], svn=[], ignores=[])

    @staticmethod
    def test_scan_for_folder_candidates_nosuchdir():
        actual = scan_for_folder_candidates(Path("DOESNOTEXIST!"))
        assert actual == FolderCandidates(git=[], svn=[], ignores=[])

    @staticmethod
    def test_scan_for_folder_candidates(tmp_path):
        # prepare
        subdir = tmp_path.joinpath("subdir")
        # git
        gitdirs = []
        for i in range(3):
            gitdir = subdir.joinpath(f"gitdir_{i}")
            gitdirs.append(gitdir)
            gitdir.mkdir(parents=True)
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            # remote is needed otherwise it would be ignored
            subprocess.call(shlex.split("git remote add origin file://."), cwd=gitdir)
        # SVN
        svndirs = []
        for i in range(3):
            svndir = subdir.joinpath(f"svndir_{i}")
            svndirs.append(svndir)
            svndir.joinpath(".svn/").mkdir(parents=True)
        # ignore dirs
        for dirname in DIRS_TO_IGNORE:
            subdir.joinpath(dirname).mkdir()
        # action
        actual = scan_for_folder_candidates(subdir)
        # check
        assert actual == FolderCandidates(git=gitdirs, svn=svndirs, ignores=[])

    @staticmethod
    def test_scan_for_folder_candidates__ignore(tmp_path, caplog):
        # prepare
        subdir = tmp_path.joinpath("subdir")
        dirs = []
        ignored = None
        for i in range(3):
            gitdir = subdir.joinpath(f"gitdir_{i}")
            gitdir.mkdir(parents=True)
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            # remote is needed otherwise it would be ignored
            subprocess.call(shlex.split("git remote add origin file://."), cwd=gitdir)
            if i == 2:
                # place ignorefile
                with gitdir.joinpath(IGNORE_FILE).open("w", encoding="utf8") as fout:
                    fout.write("")
                ignored = gitdir
            else:
                # do not include this gitdir (because ignored)
                dirs.append(gitdir)
        # action
        actual = scan_for_folder_candidates(subdir)
        # check
        assert actual == FolderCandidates(git=dirs, svn=[], ignores=[ignored])
        assert caplog.messages[0] == f"Ignore file found, *recursively* ignoring {ignored.resolve()}"

    @staticmethod
    def test_scan_for_folder_candidates__nogitpush(tmp_path, caplog):
        # prepare
        subdir = tmp_path.joinpath("subdir")
        dirs = []
        ignored = None
        for i in range(3):
            gitdir = subdir.joinpath(f"gitdir_{i}")
            gitdir.mkdir(parents=True)
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            # remote is needed otherwise it would be ignored
            subprocess.call(shlex.split("git remote add origin file://."), cwd=gitdir)
            if i == 2:
                # place ignorefile
                with gitdir.joinpath(IGNORE_FILE_NOGITPUSH).open("w", encoding="utf8") as fout:
                    fout.write("")
                ignored = gitdir
            else:
                # do not include this gitdir (because ignored)
                dirs.append(gitdir)
        # action
        actual = scan_for_folder_candidates(subdir)
        # check
        assert actual == FolderCandidates(git=dirs, svn=[], ignores=[])
        assert caplog.messages[0] == f"Ignore file found, *recursively* no git push for {ignored.resolve()}"


class TestSetupCache:

    @staticmethod
    def test_setup_cache(tmp_path):
        setup_cache(tmp_path, cache_max_age=1)

    @staticmethod
    def test_setup_cache_reread(tmp_path, caplog):
        # prepare
        caplog.set_level(logging.DEBUG)
        # prepare
        subprocess.call(shlex.split("git init"), cwd=tmp_path)
        subprocess.call(shlex.split("git remote add origin file://."), cwd=tmp_path)
        subprocess.call(shlex.split("git remote set-url --push origin ''"), cwd=tmp_path)
        setup_cache(tmp_path, cache_max_age=1)
        # action
        _, candidates = setup_cache(tmp_path, cache_max_age=2)
        # check
        assert candidates == FolderCandidates(git=[tmp_path], svn=[], ignores=[])


class TestMain:

    @staticmethod
    def test_main(monkeypatch, tmp_path, caplog, capsys):
        # prepare
        caplog.set_level(logging.DEBUG)

        def prepare_git_remote():
            """Create the git 'remote'."""
            remote = tmp_path.joinpath("git_remote/")
            remote.mkdir(parents=True)
            subprocess.call(shlex.split("git init --bare"), cwd=remote)
            return remote

        def prepare_git_dir(remote: Path):
            """Create a simple git target folder."""
            gitdir = tmp_path.joinpath("gitdir/", "subdir/")
            gitdir.mkdir(parents=True)
            # init empty git working dir
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            # add remote (push url)
            subprocess.call(shlex.split(f"git remote add origin file://{remote.resolve()}"), cwd=gitdir)
            # at least 1 commit is needed
            subprocess.call(shlex.split("git commit --allow-empty -m 'foobar'"), cwd=gitdir)
            # push to the remote
            subprocess.call(shlex.split("git push origin master"), cwd=gitdir)
            # add tracking information for current branch
            subprocess.call(shlex.split("git branch --set-upstream-to=origin/master master"), cwd=gitdir)
            return gitdir

        def prepare_ignored_git_dir():
            gitdir = tmp_path.joinpath("gitdir/", "subdir_ignore/")
            gitdir.mkdir(parents=True)
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            with gitdir.joinpath(IGNORE_FILE).open("w") as fout:
                fout.write("ignore!")
            return gitdir

        def prepare_git_dir_noremote():
            gitdir = tmp_path.joinpath("gitdir/", "subdir_noremote/")
            gitdir.mkdir(parents=True)
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            return gitdir

        def prepare_git_dir_badremote():
            gitdir = tmp_path.joinpath("gitdir/", "subdir_badremote/")
            gitdir.mkdir(parents=True)
            subprocess.call(shlex.split("git init"), cwd=gitdir)
            subprocess.call(shlex.split("git remote add origin file:///DOESNOTEXIST"), cwd=gitdir)
            return gitdir

        # create git dirs
        git_remote = prepare_git_remote()
        git_dir = prepare_git_dir(git_remote)
        git_ignore = prepare_ignored_git_dir()
        git_noremote = prepare_git_dir_noremote()
        git_badremote = prepare_git_dir_badremote()
        # argv
        monkeypatch.setattr(sys, "argv", ["_", str(tmp_path.resolve()), "--git-push"])
        # action
        main()
        # check
        assert tmp_path.joinpath(FolderCandidatesCache.CACHE_FILE)
        assert len(caplog.messages) == 27
        assert caplog.messages[0] == f"basepath: {tmp_path.resolve()}"
        assert caplog.messages[1] == f"cache_file: {tmp_path.joinpath(FolderCandidatesCache.CACHE_FILE).resolve()}"
        assert caplog.messages[2] == 'outdated_age_max_days: 1.00'
        assert caplog.messages[3] == 'No cache file found or cache is outdated! Updating cache ...'
        assert caplog.messages[4] == 'Scanning for all folder candidates ...'
        assert caplog.messages[5] == f"Ignore file found, *recursively* ignoring {git_ignore.resolve()}"
        assert caplog.messages[6] == 'Updating cache ...'
        assert caplog.messages[7] == 'Processing 3 git directories ...'
        assert caplog.messages[8] == f"(1/3) Updating git repository '{git_dir.resolve()}' ..."
        assert caplog.messages[9] == f"running command: git remote -v show -n (cwd:{git_dir.resolve()})"
        assert caplog.messages[10] == f"push_url: file://{git_remote.resolve()}"
        assert caplog.messages[11] == f"running command: git pull --recurse-submodules --all (cwd:{git_dir.resolve()})"
        assert caplog.messages[12] == f"running command: git push --all (cwd:{git_dir.resolve()})"
        assert caplog.messages[13] == f"(2/3) Updating git repository '{git_badremote.resolve()}' ..."
        assert caplog.messages[14] == f"running command: git remote -v show -n (cwd:{git_badremote.resolve()})"
        assert caplog.messages[15] == 'push_url: file:///DOESNOTEXIST'
        assert caplog.messages[16] == (f"running command: git pull --recurse-submodules --all "
                                       f"(cwd:{git_badremote.resolve()})")
        assert caplog.messages[17] == 'git pull error! (return code: 1)'
        assert caplog.messages[18] == f"(3/3) Updating git repository '{git_noremote.resolve()}' ..."
        assert caplog.messages[19] == f"running command: git remote -v show -n (cwd:{git_noremote.resolve()})"
        assert caplog.messages[20] == 'push_url: None'
        assert caplog.messages[21] == 'No git pull possible - skipping ...'
        assert caplog.messages[22] == 'All done.\n------------------------------------------------------------\n'
        assert caplog.messages[23] == f"overview for ignored:\n{git_ignore.resolve()}\tignored"
        assert caplog.messages[24] == f"overview for OK:\n{git_dir.resolve()}\tgit pull + push OK"
        assert caplog.messages[25] == (f"overview for errors:\n{git_badremote.resolve()}	git pull error! "
                                       f"(return code: 1)\n{git_noremote.resolve()}	no git pull possible")
        assert caplog.messages[26] == '1 OK, 1 ignored, 2 errors'
        stdout, stderr = capsys.readouterr()
        assert stdout == 'Already up to date.\n'
        assert stderr == ("fatal: '/DOESNOTEXIST' does not appear to be a git repository\n"
                          'fatal: Could not read from remote repository.\n'
                          '\n'
                          'Please make sure you have the correct access rights\n'
                          'and the repository exists.\n')
