#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
uv run --locked python manage.py rundramatiq --processes 1 --threads 2
popd
