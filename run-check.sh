#!/bin/sh
exec poetry run pre-commit run --all-files "$@"
