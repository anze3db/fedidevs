#!/bin/bash
set -e
cd "$(dirname "$0")/.."
export NEW_RELIC_CONFIG_FILE=/var/apps/fedidevs/newrelic.ini
exec .venv/bin/newrelic-admin run-program .venv/bin/python manage.py potatoq worker --loglevel=INFO --concurrency=4
