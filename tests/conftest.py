"""Local conftest.py plugins contain directory-specific hook implementations."""

import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path

import pytest
from loguru import logger

from recursivegitupdate.utils.git_utils import call_git
from tests.utilities import git_add_remote, git_init

# make sure messages are given in English
os.environ["LANG"] = "en"


@pytest.fixture(autouse=True)
def _chdir_to_tests(monkeypatch):
    """Change CWD to tests/ dir for each test (thread-safe via monkeypatch)."""
    tests_dir = Path(__file__).parent.resolve()
    monkeypatch.chdir(tests_dir)


@pytest.fixture(autouse=True)
def _isolated_tempdir(monkeypatch, tmp_path_factory):
    """Keep the folder cache out of the real temp directory (and out of the scanned ``tmp_path``)."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path_factory.mktemp("systmp")))


@pytest.fixture(autouse=True)
def _reset_loguru():
    """Drop all loguru sinks after each test (e.g., sinks pointing to already closed CLI-runner streams)."""
    yield
    logger.remove()


@pytest.fixture
def caplog(caplog):
    """Make loguru records visible in pytest's caplog.

    Honours ``caplog.set_level()`` like stdlib logging does: records below the root logger level
    (WARNING by default) are not captured.
    """
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= logging.getLogger().level,
    )
    yield caplog
    with suppress(ValueError):
        logger.remove(handler_id)


@pytest.fixture
def make_git_repo(tmp_path):
    """Create a git repository with a bare remote and tracking branch.

    Usage:
        workdir, remote = make_git_repo()
        workdir, remote = make_git_repo(workdir=custom_path)
        workdir, remote = make_git_repo(workdir=custom_path, remote=custom_remote)
    """
    _counter = [0]

    def _make(workdir: Path | None = None, remote: Path | None = None) -> tuple[Path, Path]:
        _counter[0] += 1
        if remote is None:
            remote = tmp_path / f"_remote_{_counter[0]}"
        if workdir is None:
            workdir = tmp_path / f"_work_{_counter[0]}"

        remote.mkdir(parents=True, exist_ok=True)
        call_git("init", "--bare", "--initial-branch", "main", cwd=remote)

        workdir.mkdir(parents=True, exist_ok=True)
        git_init(workdir)
        git_add_remote(workdir, f"file://{remote.resolve()}")
        call_git("commit", "--allow-empty", "-m", "init", cwd=workdir)
        call_git("push", "origin", "main", cwd=workdir)
        call_git("branch", "--set-upstream-to=origin/main", "main", cwd=workdir)

        return workdir, remote

    return _make
