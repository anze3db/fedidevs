#!/bin/bash
set -e
pushd "../$(dirname "$0")"
uv run python manage.py scheduler
popd
