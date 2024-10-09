#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
uv run --frozen gunicorn fedidevs.wsgi
popd
