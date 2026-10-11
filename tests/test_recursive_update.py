"""Unit tests for recursive_update module."""

import logging
import shutil
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired
from unittest.mock import patch

import pytest

from recursivegitupdate.foldercandidatescache import FolderCandidatesCache
from recursivegitupdate.models import CACHE_VERSION, FolderCandidates, Results
from recursivegitupdate.recursive_update import (
    _do_git_pull,
    _do_git_push,
    _process_git,
    _process_svn,
    _should_skip_push,
    _show_overview_category,
    run,
    setup_cache,
)
from recursivegitupdate.utils.git_utils import call_git
from tests.utilities import git_add_remote, git_disable_push, git_init

# ============================================================
# setup_cache
# ============================================================


class TestSetupCache:
    @staticmethod
    def test_creates_cache_file(tmp_path):
        cache, candidates = setup_cache(tmp_path, cache_max_age=1)
        assert cache.cache_filepath.exists()
        assert not any(tmp_path.iterdir())  # nothing is written into the scanned tree
        assert isinstance(candidates, FolderCandidates)

    @staticmethod
    def test_uses_existing_cache(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        # prepare - create repo & initial cache
        git_init(tmp_path)
        git_add_remote(tmp_path, "file:///.")
        git_disable_push(tmp_path)
        setup_cache(tmp_path, cache_max_age=1)
        caplog.clear()
        # action - reload from cache
        _, candidates = setup_cache(tmp_path, cache_max_age=2)
        # check
        assert candidates == FolderCandidates(git=[tmp_path], svn=[], ignores=[])
        assert any("Using cache" in msg for msg in caplog.messages)

    @staticmethod
    def test_cache_for_other_basepath_is_ignored(tmp_path, caplog):
        """A cache file which belongs to a different basepath (e.g., hash collision) triggers a rescan."""
        # create cache for tmp_path
        cache, _ = setup_cache(tmp_path, cache_max_age=1)
        # make the cache file of another basepath point to it
        other_path = tmp_path / "other"
        other_path.mkdir()
        other_cache = FolderCandidatesCache.for_basepath(other_path)
        shutil.copy(cache.cache_filepath, other_cache.cache_filepath)
        (other_path / "repo" / ".git").mkdir(parents=True)
        # action
        _, candidates = setup_cache(other_path, cache_max_age=2)
        # check
        assert candidates.git == (other_path / "repo",)
        assert any("Cache file belongs to" in msg for msg in caplog.messages)

    @staticmethod
    def test_cache_version_mismatch_rescans(tmp_path, caplog):
        """A cache file from another program version is rebuilt instead of crashing."""
        cache_file = FolderCandidatesCache.for_basepath(tmp_path).cache_filepath
        cache_file.write_text(
            f'{{"root": "{tmp_path}", "candidates": {{}}, "cache_version": 1}}',
            encoding="utf8",
        )
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        # action
        _, candidates = setup_cache(tmp_path, cache_max_age=1)
        # check
        assert candidates.git == (tmp_path / "repo",)
        assert any("Ignoring invalid cache file" in msg for msg in caplog.messages)
        assert f'"cache_version": {CACHE_VERSION}' in cache_file.read_text(encoding="utf8")


# ============================================================
# _should_skip_push
# ============================================================


class TestShouldSkipPush:
    @staticmethod
    @pytest.mark.parametrize(
        "url,expected",
        [
            (None, True),
            ("", True),
            ("https://github.com/user/repo.git", True),
            ("git@github.com:user/repo.git", True),
            ("ssh://git@myserver/repo.git", False),
            ("https://gitlab.com/user/repo.git", False),
            ("file:///local/path", False),
        ],
    )
    def test_skip_decision(url, expected):
        assert _should_skip_push(url) is expected


# ============================================================
# _do_git_pull / _do_git_push
# ============================================================


class TestDoGitPull:
    @staticmethod
    def test_dry_run(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        ok, msg = _do_git_pull(tmp_path, dry_run=True)
        assert ok is True
        assert "dry-run" in msg
        assert any("[DRY-RUN]" in m for m in caplog.messages)

    @staticmethod
    def test_dry_run_with_extra_args(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        ok, _ = _do_git_pull(tmp_path, dry_run=True, extra_args=["--rebase"])
        assert ok is True
        assert any("--rebase" in m for m in caplog.messages)

    @staticmethod
    def test_success(make_git_repo):
        workdir, _ = make_git_repo()
        ok, msg = _do_git_pull(workdir, dry_run=False)
        assert ok is True
        assert msg == "git pull OK"

    @staticmethod
    def test_failure(tmp_path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        git_init(workdir)
        git_add_remote(workdir, "file:///DOESNOTEXIST")
        ok, msg = _do_git_pull(workdir, dry_run=False)
        assert ok is False
        assert "git pull error" in msg

    @staticmethod
    def test_extra_args_passed(make_git_repo, caplog):
        """Extra args are included in the git command."""
        workdir, _ = make_git_repo()
        caplog.set_level(logging.DEBUG)
        ok, _ = _do_git_pull(workdir, dry_run=False, extra_args=["--no-rebase"])
        # Should succeed (--no-rebase is valid)
        assert ok is True
        assert any("--no-rebase" in m for m in caplog.messages)

    @staticmethod
    def test_extra_args_quoted(tmp_path, caplog):
        """Extra args are passed as separate arguments, so values with blanks stay one argument."""
        caplog.set_level(logging.DEBUG)
        _do_git_pull(tmp_path, dry_run=True, extra_args=["-X", "ours theirs"])
        assert any("--all -X 'ours theirs'" in m for m in caplog.messages)


class TestDoGitPush:
    @staticmethod
    def test_dry_run(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        ok, msg = _do_git_push(tmp_path, dry_run=True)
        assert ok is True
        assert "dry-run" in msg
        assert any("[DRY-RUN]" in m for m in caplog.messages)

    @staticmethod
    def test_success(make_git_repo):
        workdir, _ = make_git_repo()
        ok, msg = _do_git_push(workdir, dry_run=False)
        assert ok is True
        assert "push OK" in msg


# ============================================================
# _process_git
# ============================================================


class TestProcessGit:
    @staticmethod
    def _make_cache(tmp_path):
        cache_file = tmp_path / "cache.json"
        return FolderCandidatesCache(cache_file, outdated_age_max_days=1)

    def test_empty_list(self, tmp_path):
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([], cache, results, git_do_push=False)
        assert len(results.ok) == 0
        assert len(results.error) == 0

    def test_nonexistent_dir_invalidates_cache(self, tmp_path):
        cache = self._make_cache(tmp_path)
        results = Results()
        folders = [tmp_path / "DOESNOTEXIST"]
        with patch.object(cache, "invalidate") as mock_inv:
            _process_git(folders, cache, results, git_do_push=False)
            mock_inv.assert_called_once()

    def test_pull_success(self, tmp_path, make_git_repo):
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([workdir], cache, results, git_do_push=False)
        assert workdir in results.ok
        assert "git pull OK" in results.ok[workdir]

    def test_nopush_pulls_but_does_not_push(self, tmp_path, make_git_repo, caplog):
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        caplog.set_level(logging.DEBUG)
        cache = self._make_cache(tmp_path)
        results = Results()
        with patch("recursivegitupdate.recursive_update._do_git_push") as mock_push:
            _process_git([workdir], cache, results, git_do_push=True, nopush={workdir})
        mock_push.assert_not_called()
        assert results.ok[workdir] == "git pull OK"
        assert any("no-git-push marker" in m for m in caplog.messages)

    def test_pull_and_push_success(self, tmp_path, make_git_repo):
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([workdir], cache, results, git_do_push=True)
        assert workdir in results.ok
        assert "push OK" in results.ok[workdir]

    def test_pull_failure(self, tmp_path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        git_init(workdir)
        git_add_remote(workdir, "file:///DOESNOTEXIST")
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([workdir], cache, results, git_do_push=False)
        assert workdir in results.error
        assert "git pull error" in results.error[workdir]

    def test_no_remote_skips(self, tmp_path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        git_init(workdir)
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([workdir], cache, results, git_do_push=False)
        assert workdir in results.error
        assert "no git pull possible" in results.error[workdir]

    def test_github_push_skipped(self, tmp_path, make_git_repo, caplog):
        """Push to github.com remotes is skipped."""
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        # override push URL to contain github.com
        call_git("remote", "set-url", "--push", "origin", "https://github.com/user/repo.git", cwd=workdir)
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([workdir], cache, results, git_do_push=True)
        assert workdir in results.ok
        assert results.ok[workdir] == "git pull OK"  # no push performed
        assert any("github.com" in msg for msg in caplog.messages)

    def test_remote_check_failure_is_handled(self, tmp_path, caplog):
        """CalledProcessError from check_git_pullpush is caught gracefully."""
        workdir = tmp_path / "work"
        workdir.mkdir()
        git_init(workdir)
        git_add_remote(workdir, "file:///.")
        caplog.set_level(logging.DEBUG)
        cache = self._make_cache(tmp_path)
        results = Results()
        with patch(
            "recursivegitupdate.recursive_update.check_git_pullpush", side_effect=CalledProcessError(128, "git")
        ):
            _process_git([workdir], cache, results, git_do_push=False)
        assert workdir in results.error
        assert "remote check failed" in results.error[workdir]

    def test_remote_check_timeout_is_handled(self, tmp_path):
        """TimeoutExpired from check_git_pullpush is recorded as error instead of aborting the run."""
        workdir = tmp_path / "work"
        workdir.mkdir()
        cache = self._make_cache(tmp_path)
        results = Results()
        with patch("recursivegitupdate.recursive_update.check_git_pullpush", side_effect=TimeoutExpired("git", 30)):
            _process_git([workdir], cache, results, git_do_push=False)
        assert workdir in results.error
        assert "remote check failed" in results.error[workdir]

    def test_push_failure_removes_from_ok(self, tmp_path, make_git_repo):
        """On push failure, folder is in error only (not in ok)."""
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        cache = self._make_cache(tmp_path)
        results = Results()
        with patch(
            "recursivegitupdate.recursive_update._do_git_push", return_value=(False, "git push error! (return code: 1)")
        ):
            _process_git([workdir], cache, results, git_do_push=True)
        # Folder must NOT be in both ok and error
        assert workdir in results.error
        assert workdir not in results.ok
        assert "push error" in results.error[workdir]

    def test_extra_args_forwarded(self, tmp_path, make_git_repo, caplog):
        """--git-args are passed through to git pull."""
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        caplog.set_level(logging.DEBUG)
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git([workdir], cache, results, git_do_push=False, extra_args=["--no-rebase"])
        assert workdir in results.ok
        assert any("--no-rebase" in m for m in caplog.messages)

    def test_accepts_tuple_input(self, tmp_path, make_git_repo):
        """_process_git accepts tuple (from FolderCandidates)."""
        workdir, _ = make_git_repo(workdir=tmp_path / "work")
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_git((workdir,), cache, results, git_do_push=False)
        assert workdir in results.ok


# ============================================================
# _process_svn
# ============================================================


class TestProcessSvn:
    @staticmethod
    def _make_cache(tmp_path):
        cache_file = tmp_path / "cache.json"
        return FolderCandidatesCache(cache_file, outdated_age_max_days=1)

    def test_empty_list(self, tmp_path):
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_svn([], cache, results)
        assert len(results.ok) == 0
        assert len(results.error) == 0

    def test_nonexistent_dir_invalidates_cache(self, tmp_path):
        cache = self._make_cache(tmp_path)
        results = Results()
        folders = [tmp_path / "DOESNOTEXIST"]
        with patch.object(cache, "invalidate") as mock_inv:
            _process_svn(folders, cache, results)
            mock_inv.assert_called_once()

    def test_svn_up_failure(self, tmp_path):
        """svn up returning non-zero is recorded as error."""
        workdir = tmp_path / "notsvn"
        workdir.mkdir()
        cache = self._make_cache(tmp_path)
        results = Results()
        with patch("recursivegitupdate.recursive_update.run_command", return_value=1):
            _process_svn([workdir], cache, results)
        assert workdir in results.error
        assert "svn ERROR" in results.error[workdir]

    def test_svn_dry_run(self, tmp_path, caplog):
        """In dry-run mode, svn up is NOT executed."""
        workdir = tmp_path / "svnrepo"
        workdir.mkdir()
        caplog.set_level(logging.DEBUG)
        cache = self._make_cache(tmp_path)
        results = Results()
        _process_svn([workdir], cache, results, dry_run=True)
        assert workdir in results.ok
        assert "dry-run" in results.ok[workdir]
        assert any("[DRY-RUN]" in msg for msg in caplog.messages)

    def test_accepts_tuple_input(self, tmp_path):
        """_process_svn accepts tuple (from FolderCandidates)."""
        workdir = tmp_path / "svnrepo"
        workdir.mkdir()
        cache = self._make_cache(tmp_path)
        results = Results()
        with patch("recursivegitupdate.recursive_update.run_command", return_value=0):
            _process_svn((workdir,), cache, results)
        assert workdir in results.ok


# ============================================================
# _show_overview_category
# ============================================================


class TestShowOverviewCategory:
    @staticmethod
    def test_empty_data(caplog):
        caplog.set_level(logging.DEBUG)
        _show_overview_category("test", "INFO", {})
        assert not any("overview" in msg for msg in caplog.messages)

    @staticmethod
    def test_with_data(caplog):
        caplog.set_level(logging.DEBUG)
        data = {Path("/a"): "msg_a", Path("/b"): "msg_b"}
        _show_overview_category("OK", "INFO", data)
        assert any("overview for OK" in msg for msg in caplog.messages)
        assert any("/a\tmsg_a" in msg for msg in caplog.messages)
        assert any("/b\tmsg_b" in msg for msg in caplog.messages)

    @staticmethod
    def test_log_level_error(caplog):
        caplog.set_level(logging.DEBUG)
        data = {Path("/x"): "broken"}
        _show_overview_category("errors", "ERROR", data)
        record = next(r for r in caplog.records if "overview" in r.message)
        assert record.levelno == logging.ERROR


# ============================================================
# run
# ============================================================


class TestRun:
    @staticmethod
    def test_run_empty_dir(tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        result = run(tmp_path, cache_max_age=0, git_do_push=False)
        assert result == 0
        assert any("All done" in msg for msg in caplog.messages)

    @staticmethod
    def test_run_with_git_repo(tmp_path, make_git_repo, caplog):
        make_git_repo(workdir=tmp_path / "repos" / "myrepo")
        caplog.set_level(logging.DEBUG)
        result = run(tmp_path, cache_max_age=0, git_do_push=False)
        assert result == 0
        assert any("git pull OK" in msg for msg in caplog.messages)

    @staticmethod
    def test_run_returns_one_on_errors(tmp_path, caplog):
        """run() returns 1 when errors occur."""
        workdir = tmp_path / "repos" / "broken"
        workdir.mkdir(parents=True)
        git_init(workdir)
        git_add_remote(workdir, "file:///DOESNOTEXIST")
        caplog.set_level(logging.DEBUG)
        result = run(tmp_path, cache_max_age=0, git_do_push=False)
        assert result == 1

    @staticmethod
    def test_run_dry_run(tmp_path, make_git_repo, caplog):
        """run() with dry_run=True logs dry-run message."""
        make_git_repo(workdir=tmp_path / "repos" / "myrepo")
        caplog.set_level(logging.DEBUG)
        result = run(tmp_path, cache_max_age=0, git_do_push=False, dry_run=True)
        assert result == 0
        assert any("Dry-run mode enabled" in msg for msg in caplog.messages)
        assert any("[DRY-RUN]" in msg and "git pull" in msg for msg in caplog.messages)

    @staticmethod
    def test_run_with_extra_args(tmp_path, make_git_repo, caplog):
        """run() passes extra_args to git pull."""
        make_git_repo(workdir=tmp_path / "repos" / "myrepo")
        caplog.set_level(logging.DEBUG)
        result = run(tmp_path, cache_max_age=0, git_do_push=False, extra_args=["--no-rebase"])
        assert result == 0
        assert any("--no-rebase" in msg for msg in caplog.messages)
