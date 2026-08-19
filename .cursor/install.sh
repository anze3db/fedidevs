#!/usr/bin/env bash
# Idempotent bootstrap for the fedidevs Cloud Agent environment.
# Installs uv + PostgreSQL, syncs Python/Node deps, prepares the dev database,
# and builds static assets. Safe to run repeatedly.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# --- uv (Python toolchain + package manager) -------------------------------
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# --- PostgreSQL (required: app uses full-text search / to_tsvector) --------
if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-contrib
fi

PG_VER="$(ls /etc/postgresql | sort -n | tail -1)"
sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
for _ in $(seq 1 30); do
  sudo -u postgres pg_isready -q && break
  sleep 1
done

# Match the credentials used by CI (.github/workflows/python.yml).
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER USER postgres WITH PASSWORD 'postgres_password';"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='fedidevs'" | grep -q 1; then
  sudo -u postgres createdb fedidevs
fi

# --- Local dev configuration (.env is gitignored) --------------------------
if [ ! -f .env ]; then
  cat > .env <<'ENV'
DEBUG=True
DATABASE_URL=postgresql://postgres:postgres_password@127.0.0.1:5432/fedidevs
ENV
fi

# --- Python dependencies ---------------------------------------------------
uv sync --locked

# --- Database schema + static assets ---------------------------------------
uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput

# --- Tailwind (Node) assets ------------------------------------------------
uv run python manage.py tailwind install
