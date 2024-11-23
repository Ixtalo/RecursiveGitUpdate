# -*- coding: utf-8 -*-
"""Unit tests."""
import logging
import sys
from pathlib import Path

from recursivegitupdate.foldercandidatescache import FolderCandidatesCache
from recursivegitupdate.recursive_update import (
    scan_for_folder_candidates,
    FolderCandidates,
    IGNORE_FILE,
    IGNORE_FILE_NOGITPUSH,
    DIRS_TO_IGNORE,
    setup_cache,
    main
)
from recursivegitupdate.utils.git_utils import call_git
from tests.utilities import git_add_remote, git_init, git_disable_push


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
            git_init(gitdir)
            git_add_remote(gitdir, "file:///.")
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
            git_init(gitdir)
            git_add_remote(gitdir, "file:///.")
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
            git_init(gitdir)
            git_add_remote(gitdir, "file:///.")
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
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        git_disable_push(tmp_path)
        setup_cache(tmp_path, cache_max_age=1)
        # action
        _, candidates = setup_cache(tmp_path, cache_max_age=2)
        # check
        assert candidates == FolderCandidates(git=[tmp_path], svn=[], ignores=[])


class TestMain:

    @staticmethod
    def test_main(monkeypatch, tmp_path, caplog, capsys):
        def prepare_git_remote():
            """Create the git 'remote'."""
            remote = tmp_path.joinpath("git_remote/")
            remote.mkdir(parents=True)
            call_git("init --bare --initial-branch main", cwd=remote)
            return remote

        def prepare_git_dir(remote: Path):
            """Create a simple git target folder."""
            gitdir = tmp_path.joinpath("gitdir/", "subdir/")
            gitdir.mkdir(parents=True)
            # init empty git working dir
            git_init(gitdir)
            git_add_remote(gitdir, f"file://{remote.resolve()}")
            # at least 1 commit is needed
            call_git("commit --allow-empty -m 'foobar'", cwd=gitdir)
            # push to the remote
            call_git("push origin main", cwd=gitdir)
            # add tracking information for current branch
            call_git("branch --set-upstream-to=origin/main main", cwd=gitdir)
            return gitdir

        def prepare_ignored_git_dir():
            gitdir = tmp_path.joinpath("gitdir/", "subdir_ignore/")
            gitdir.mkdir(parents=True)
            git_init(gitdir)
            with gitdir.joinpath(IGNORE_FILE).open("w") as fout:
                fout.write("ignore!")
            return gitdir

        def prepare_git_dir_noremote():
            gitdir = tmp_path.joinpath("gitdir/", "subdir_noremote/")
            gitdir.mkdir(parents=True)
            git_init(gitdir)
            return gitdir

        def prepare_git_dir_badremote():
            gitdir = tmp_path.joinpath("gitdir/", "subdir_badremote/")
            gitdir.mkdir(parents=True)
            git_init(gitdir)
            git_add_remote(gitdir, "file:///DOESNOTEXIST")
            return gitdir

        # create git dirs
        git_remote = prepare_git_remote()
        prepare_git_dir(git_remote)
        prepare_ignored_git_dir()
        prepare_git_dir_noremote()
        prepare_git_dir_badremote()
        caplog.set_level(logging.DEBUG)
        capsys.readouterr()  # reset internal buffer, start capturing fresh
        # argv
        monkeypatch.setattr(sys, "argv", ["_", str(tmp_path.resolve()), "--git-push"])
        # action
        main()
        # check
        assert tmp_path.joinpath(FolderCandidatesCache.CACHE_FILE)

        # use debug to get the value
        messages_copied_from_debug_mode = [
            'basepath: TMPDIR',
            'cache_file: TMPDIR/.recursive_rcs_update.cache',
            'outdated_age_max_days: 1.00',
            'No cache file found or cache is outdated! Updating cache ...',
            'Scanning for all folder candidates ...',
            'Ignore file found, *recursively* ignoring '
            'TMPDIR/gitdir/subdir_ignore',
            'Updating cache ...',
            'Processing 3 git directories ...',
            "(1/3) Updating git repository 'TMPDIR/gitdir/subdir' ...",
            'running command: /usr/bin/git remote --verbose (cwd:TMPDIR/gitdir/subdir)',
            'push_url: file://TMPDIR/git_remote',
            'running command: /usr/bin/git pull --recurse-submodules --all (cwd:TMPDIR/gitdir/subdir)',
            'running command: /usr/bin/git push --all (cwd:TMPDIR/gitdir/subdir)',
            "(2/3) Updating git repository 'TMPDIR/gitdir/subdir_badremote' ...",
            'running command: /usr/bin/git remote --verbose (cwd:TMPDIR/gitdir/subdir_badremote)',
            'push_url: file:///DOESNOTEXIST',
            'running command: /usr/bin/git pull --recurse-submodules --all (cwd:TMPDIR/gitdir/subdir_badremote)',
            'git pull error! (return code: 1)',
            "(3/3) Updating git repository 'TMPDIR/gitdir/subdir_noremote' ...",
            'running command: /usr/bin/git remote --verbose (cwd:TMPDIR/gitdir/subdir_noremote)',
            'push_url: None',
            'No git pull possible - skipping ...',
            'All done.\n------------------------------------------------------------\n',
            'overview for ignored:\n'
            'TMPDIR/gitdir/subdir_ignore\tignored',
            'overview for OK:\nTMPDIR/gitdir/subdir\tgit pull + push OK',
            'overview for errors:\nTMPDIR/gitdir/subdir_badremote\tgit pull error! (return code: 1)\n'
            'TMPDIR/gitdir/subdir_noremote\tno git pull possible',
            '1 OK, 1 ignored, 2 errors'
        ]
        # adjust message strings to reflect actual runtime settings
        messages = [msg.replace("TMPDIR", str(tmp_path.resolve())) for msg in messages_copied_from_debug_mode]
        # check logging output
        assert caplog.messages == messages
        # check STDOUT+STDERR
        stdout, stderr = capsys.readouterr()
        # sometimes (other git version?) the stdout differs,
        # e.g., 'Fetching origin\nAlready up to date.\nFetchin  'Already up to date.\n
        assert 'Already up to date.\n' in stdout
        # sometimes (other git version?) the stderr differs
        assert ("fatal: '/DOESNOTEXIST' does not appear to be a git repository\n"
                'fatal: Could not read from remote repository.\n'
                '\n'
                'Please make sure you have the correct access rights\n'
                'and the repository exists.\n') in stderr
