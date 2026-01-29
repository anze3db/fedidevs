#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
export NEW_RELIC_CONFIG_FILE=/var/apps/fedidevs/newrelic.ini
/var/apps/fedidevs/.venv/bin/newrelic-admin run-program /var/apps/fedidevs/.venv/bin/python manage.py rundramatiq --processes 1 --threads 2
popd
