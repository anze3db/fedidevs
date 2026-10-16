#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
git pull
uv sync --locked
uv run python manage.py compilemessages
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate
# Periodic jobs moved into the potatoq worker; stop the old scheduler so jobs don't run twice.
sudo systemctl stop fedidevs-scheduler || true
sudo systemctl daemon-reload
sudo systemctl reload fedidevs
sudo systemctl restart fedidevs-worker
echo `date "+%Y-%m-%d %H:%M:%S.%3N"` ' Updated' >> update.log
popd
