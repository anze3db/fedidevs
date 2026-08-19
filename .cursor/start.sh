#!/usr/bin/env bash
# Per-boot startup for the fedidevs Cloud Agent environment.
# PostgreSQL data persists in the snapshot, but the server process does not,
# so start it here and apply any pending migrations from the checked-out branch.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
export PATH="$HOME/.local/bin:$PATH"

PG_VER="$(ls /etc/postgresql | sort -n | tail -1)"
sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
for _ in $(seq 1 30); do
  sudo -u postgres pg_isready -q && break
  sleep 1
done

uv run python manage.py migrate --noinput
