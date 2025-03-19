#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
NEW_RELIC_CONFIG_FILE=newrelic.ini uv run --locked newrelic-admin run-program manage.py rundramatiq --processes 1 --threads 2
popd
