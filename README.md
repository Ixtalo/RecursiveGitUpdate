# Recursive Updating of GIT/SVN Repositories

Recursively update GIT and SVN directories.

Find folders which are managed by Revision-/Version-Control-System (RCS/VCS)
tools, e.g., Git or Subversion (SVN), and update them (e.g., git pull).

## Requirements

* Python 3.10+
* Poetry 2+ (see https://python-poetry.org/docs/#installation)

## Usage

1. set up: `poetry sync --only=main` (once)
2. `poetry run recursive-git-update --help`

Alternatively, without Poetry: `pipx install .` and then `recursive-git-update --help`.

```
recursive-git-update [OPTIONS] BASEPATH
```

| Option                | Description                                                          |
|-----------------------|----------------------------------------------------------------------|
| `BASEPATH`            | Starting path for recursive folder scan.                             |
| `--cache-max-age N`   | Maximum age of the folder cache in days (float, default: 1).         |
| `--dry-run`           | Show what would be done without actually executing commands.         |
| `--git-push`          | Allow pushing for git (default is only to pull).                     |
| `--git-args ARGS`     | Additional arguments appended to `git pull` (split shell-like).      |
| `-v`, `--verbose`     | Be verbose (also enabled by the environment variable `DEBUG=1`).     |
| `--version`           | Show version.                                                        |

Exit codes: `0` success, `1` at least one repository failed to update, `2` invalid usage
(e.g., `BASEPATH` does not exist).

The folder cache is stored outside of the scanned tree, in a private per-user directory of the system's temp folder
(`<tmp>/recursivegitupdate-<user>/<hash of BASEPATH>.json`), i.e., each `BASEPATH` has its own cache.
On POSIX systems the directory must be owned by the current user and is restricted to mode `0700`,
otherwise the cache is disabled. A cache file `.recursive_rcs_update.cache` left in a `BASEPATH`
by earlier versions is no longer used and can be deleted.

Marker files inside the scanned tree:

* `.recursive_rcs_update_ignore` - ignore the whole subtree.
* `.recursive_rcs_update_no-git-push` - pull only, never push the repositories in this subtree.

## Development

* `poetry sync` installs all dependencies including the dev group.
* `poetry run pytest` runs the tests.
* `./run-check.sh` runs all pre-commit hooks (ruff lint + format, etc.).

Built with [Typer](https://typer.tiangolo.com/) (CLI), [Loguru](https://loguru.readthedocs.io/) (logging)
and [Pydantic](https://docs.pydantic.dev/) (data models and the JSON cache file).
