"""Tests for the command line interface (Typer app)."""

import pytest
from typer.testing import CliRunner

from recursivegitupdate import __version__
from recursivegitupdate.cli import app
from recursivegitupdate.foldercandidatescache import FolderCandidatesCache
from recursivegitupdate.scanner import IGNORE_FILE
from tests.utilities import git_add_remote, git_init

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_debug_env(monkeypatch):
    """Make the tests independent of a DEBUG variable in the developer's environment."""
    monkeypatch.delenv("DEBUG", raising=False)


def test_main_integration(tmp_path, make_git_repo):
    # setup repos
    make_git_repo(workdir=tmp_path / "gitdir" / "subdir")

    # ignored repo
    gitdir_ignored = tmp_path / "gitdir" / "subdir_ignore"
    gitdir_ignored.mkdir(parents=True)
    git_init(gitdir_ignored)
    (gitdir_ignored / IGNORE_FILE).touch()

    # no remote
    gitdir_noremote = tmp_path / "gitdir" / "subdir_noremote"
    gitdir_noremote.mkdir(parents=True)
    git_init(gitdir_noremote)

    # bad remote
    gitdir_bad = tmp_path / "gitdir" / "subdir_badremote"
    gitdir_bad.mkdir(parents=True)
    git_init(gitdir_bad)
    git_add_remote(gitdir_bad, "file:///DOESNOTEXIST")

    # action
    result = runner.invoke(app, [str(tmp_path.resolve()), "--git-push"])

    # check - returns 1 because of errors (bad remote, no remote)
    assert result.exit_code == 1
    assert FolderCandidatesCache.for_basepath(tmp_path).cache_filepath.exists()
    lines = result.stdout.splitlines()
    assert any("Processing" in line and "git directories" in line for line in lines)
    assert any("git pull + push OK" in line for line in lines)
    assert any("git pull error" in line for line in lines)
    assert any("No git pull possible" in line for line in lines)
    assert any("ignoring" in line for line in lines)
    assert any("OK" in line and "ignored" in line and "errors" in line for line in lines)
    assert "fatal" in result.stderr


def test_main_success_exit_code(tmp_path, make_git_repo):
    make_git_repo(workdir=tmp_path / "repos" / "myrepo")
    result = runner.invoke(app, [str(tmp_path.resolve())])
    assert result.exit_code == 0
    assert "git pull OK" in result.stdout


def test_main_dry_run_flag(tmp_path, make_git_repo):
    """--dry-run CLI flag is correctly parsed and passed through."""
    make_git_repo(workdir=tmp_path / "repos" / "myrepo")
    result = runner.invoke(app, [str(tmp_path.resolve()), "--dry-run"])
    assert result.exit_code == 0
    assert "Dry-run mode enabled" in result.stdout
    assert "[DRY-RUN]" in result.stdout


def test_main_git_args_flag(tmp_path, make_git_repo):
    """--git-args CLI flag is correctly parsed and passed through."""
    make_git_repo(workdir=tmp_path / "repos" / "myrepo")
    result = runner.invoke(app, [str(tmp_path.resolve()), "--git-args=--no-rebase", "-v"])
    assert result.exit_code == 0
    assert "--no-rebase" in result.stdout


def test_main_git_args_are_split_shell_like(tmp_path):
    """Quoted values in --git-args stay one argument."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git_init(repo)
    git_add_remote(repo, "file:///.")
    result = runner.invoke(app, [str(tmp_path), "--dry-run", "--git-args=-X 'ours theirs'"])
    assert result.exit_code == 0
    assert "--all -X 'ours theirs'" in result.stdout


def test_main_invalid_git_args_quoting(tmp_path):
    result = runner.invoke(app, [str(tmp_path), "--git-args=--foo 'unterminated"])
    assert result.exit_code == 2
    assert "--git-args" in result.output


def test_main_nonexistent_basepath(tmp_path):
    result = runner.invoke(app, [str(tmp_path / "DOESNOTEXIST")])
    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_main_negative_cache_max_age(tmp_path):
    result = runner.invoke(app, [str(tmp_path), "--cache-max-age=-1"])
    assert result.exit_code == 2


def test_main_without_arguments_shows_help():
    result = runner.invoke(app, [])
    assert "Usage" in result.output
    assert "BASEPATH" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"Recursive RCS Updater {__version__}" in result.stdout


def test_debug_env_enables_verbose_output(tmp_path, monkeypatch):
    # without DEBUG: no debug output
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 0
    assert "basepath:" not in result.stdout
    # with DEBUG
    FolderCandidatesCache.for_basepath(tmp_path).invalidate()
    monkeypatch.setenv("DEBUG", "1")
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 0
    assert "basepath:" in result.stdout


def test_debug_env_with_foreign_value_is_ignored(tmp_path, monkeypatch):
    """Values like DEBUG='*' (used by other tools) must neither fail nor enable verbose output."""
    monkeypatch.setenv("DEBUG", "*")
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 0
    assert "basepath:" not in result.stdout
