# Recursive Updating of GIT/SVN Repositories

Recursively update GIT and SVN directories.

Find folders which are managed by Revision-/Version-Control-System (RCS/VCS)
tools, e.g., Git or Subversion (SVN), and update them (e.g., git pull).

## Requirements

* Python 3.10+
* Poetry (see https://python-poetry.org/docs/#installation)

## Usage

1. set up: `poetry install --only=main --sync --no-root` (once)
2. `poetry run python recursive_rcs_update --help`
