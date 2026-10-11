"""Unit tests for the scanner module."""

import os
from pathlib import Path

import pytest

from recursivegitupdate.models import FolderCandidates
from recursivegitupdate.scanner import (
    DIRS_TO_IGNORE,
    IGNORE_FILE,
    IGNORE_FILE_NOGITPUSH,
    scan_for_folder_candidates,
)
from tests.utilities import git_add_remote, git_init


class TestScanFolderCandidates:
    @staticmethod
    def test_empty_dir(tmp_path):
        actual = scan_for_folder_candidates(tmp_path)
        assert actual == FolderCandidates(git=[], svn=[], ignores=[])

    @staticmethod
    def test_nonexistent_dir():
        actual = scan_for_folder_candidates(Path("DOESNOTEXIST!"))
        assert actual == FolderCandidates(git=[], svn=[], ignores=[])

    @staticmethod
    def test_finds_git_and_svn(tmp_path):
        # prepare
        subdir = tmp_path / "subdir"
        gitdirs = []
        for i in range(3):
            gitdir = subdir / f"gitdir_{i}"
            gitdirs.append(gitdir)
            gitdir.mkdir(parents=True)
            git_init(gitdir)
            git_add_remote(gitdir, "file:///.")
        svndirs = []
        for i in range(3):
            svndir = subdir / f"svndir_{i}"
            svndirs.append(svndir)
            (svndir / ".svn").mkdir(parents=True)
        # create dirs that should be ignored
        for dirname in DIRS_TO_IGNORE:
            (subdir / dirname).mkdir()
        # action
        actual = scan_for_folder_candidates(subdir)
        # check
        assert actual == FolderCandidates(git=gitdirs, svn=svndirs, ignores=[])

    @staticmethod
    def test_ignore_file(tmp_path, caplog):
        # prepare
        subdir = tmp_path / "subdir"
        dirs = []
        ignored = None
        for i in range(3):
            gitdir = subdir / f"gitdir_{i}"
            gitdir.mkdir(parents=True)
            git_init(gitdir)
            git_add_remote(gitdir, "file:///.")
            if i == 2:
                (gitdir / IGNORE_FILE).touch()
                ignored = gitdir
            else:
                dirs.append(gitdir)
        # action
        actual = scan_for_folder_candidates(subdir)
        # check
        assert actual == FolderCandidates(git=dirs, svn=[], ignores=[ignored])
        assert f"Ignore file found, *recursively* ignoring {ignored.resolve()}" in caplog.messages[0]

    @staticmethod
    def test_nogitpush_file(tmp_path, caplog):
        """Marker file: repo is still a candidate (pull), but flagged as no-push."""
        subdir = tmp_path / "subdir"
        dirs = []
        for i in range(3):
            gitdir = subdir / f"gitdir_{i}"
            gitdir.mkdir(parents=True)
            git_init(gitdir)
            git_add_remote(gitdir, "file:///.")
            dirs.append(gitdir)
        (dirs[2] / IGNORE_FILE_NOGITPUSH).touch()
        # action
        actual = scan_for_folder_candidates(subdir)
        # check
        assert actual == FolderCandidates(git=dirs, svn=[], ignores=[], git_nopush=[dirs[2]])
        assert f"no git push for {dirs[2].resolve()}" in caplog.messages[0]

    @staticmethod
    def test_nogitpush_file_applies_to_subtree(tmp_path):
        """Marker in a parent directory flags all repositories below it."""
        (tmp_path / "pushable" / ".git").mkdir(parents=True)
        (tmp_path / "locked" / IGNORE_FILE_NOGITPUSH).parent.mkdir()
        (tmp_path / "locked" / IGNORE_FILE_NOGITPUSH).touch()
        (tmp_path / "locked" / "a" / "b" / ".git").mkdir(parents=True)
        (tmp_path / "locked" / "c" / ".git").mkdir(parents=True)
        # action
        actual = scan_for_folder_candidates(tmp_path)
        # check
        assert tmp_path / "pushable" in actual.git
        assert tmp_path / "pushable" not in actual.git_nopush
        assert set(actual.git_nopush) == {tmp_path / "locked" / "a" / "b", tmp_path / "locked" / "c"}
        assert set(actual.git_nopush) <= set(actual.git)

    @staticmethod
    def test_nested_git_not_recursed(tmp_path):
        """Once .git is found, don't recurse deeper."""
        gitdir = tmp_path / "repo"
        gitdir.mkdir()
        git_init(gitdir)
        # nested git inside (should not be found separately)
        nested = gitdir / "submodule"
        nested.mkdir()
        (nested / ".git").mkdir()
        # action
        actual = scan_for_folder_candidates(tmp_path)
        # check - only outer repo found
        assert actual.git == (gitdir,)

    @staticmethod
    def test_git_file_is_repo(tmp_path):
        """A '.git' file (worktree, submodule) marks a repository as well."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /somewhere/else\n", encoding="utf8")
        actual = scan_for_folder_candidates(tmp_path)
        assert actual.git == (worktree,)

    @staticmethod
    def test_repo_root_not_recursed_regardless_of_sort_order(tmp_path):
        """Subdirectories sorting before '.git' are not scanned inside a repository."""
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "#nested" / ".git").mkdir(parents=True)
        actual = scan_for_folder_candidates(tmp_path)
        assert actual.git == (repo,)

    @staticmethod
    def test_dirs_to_ignore_skipped(tmp_path):
        """Directories in DIRS_TO_IGNORE are completely skipped."""
        for dirname in DIRS_TO_IGNORE:
            ignored = tmp_path / dirname
            ignored.mkdir()
            (ignored / ".git").mkdir()
        # action
        actual = scan_for_folder_candidates(tmp_path)
        # check - none found
        assert actual == FolderCandidates(git=[], svn=[], ignores=[])

    @staticmethod
    def test_returns_immutable_result(tmp_path):
        """Result is truly immutable."""
        gitdir = tmp_path / "repo"
        gitdir.mkdir()
        git_init(gitdir)
        result = scan_for_folder_candidates(tmp_path)
        with pytest.raises(AttributeError):
            result.git.append(Path("/evil"))

    @staticmethod
    @pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions")
    def test_permission_denied(tmp_path, caplog):
        """Permission denied is logged gracefully and does not abort the scan."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        restricted.chmod(0o000)
        try:
            actual = scan_for_folder_candidates(tmp_path)
        finally:
            restricted.chmod(0o755)
        assert actual.git == (tmp_path / "repo",)
        assert any("Permission denied" in msg for msg in caplog.messages)

    @staticmethod
    def test_symlinked_dirs_are_not_followed(tmp_path):
        """A symlink pointing to a repository outside of the tree does not yield a candidate."""
        outside = tmp_path / "outside"
        (outside / ".git").mkdir(parents=True)
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "link").symlink_to(outside, target_is_directory=True)
        assert scan_for_folder_candidates(tree) == FolderCandidates()
