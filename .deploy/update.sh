#!/bin/bash
set -e
pushd "$(dirname "$0")/.."
git pull
old_python=$(.venv/bin/python -V 2>&1 || true)
uv sync --locked
uv run python manage.py compilemessages
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate
# Periodic jobs moved into the potatoq worker; stop the old scheduler so jobs don't run twice.
sudo systemctl stop fedidevs-scheduler || true
sudo systemctl daemon-reload
# A new Python version means uv rebuilt .venv under the running server, so a reload isn't enough.
if [ "$old_python" != "$(.venv/bin/python -V 2>&1)" ]; then
    sudo systemctl restart fedidevs
else
    sudo systemctl reload fedidevs
fi
sudo systemctl restart fedidevs-worker
echo `date "+%Y-%m-%d %H:%M:%S.%3N"` ' Updated' >> update.log
popd
