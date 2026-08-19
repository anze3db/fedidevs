#!/usr/bin/env bash
# Per-boot startup for the fedidevs Cloud Agent environment.
# PostgreSQL data persists in the snapshot, but the server process does not,
# so start it here and apply any pending migrations from the checked-out branch.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
export PATH="$HOME/.local/bin:$PATH"

# --- Per-environment dev port ----------------------------------------------
# Pick one random high port per environment (persisted in .dev_port) so that:
#   * multiple Cloud Agents forward to distinct local ports (no collisions), and
#   * the local port the client picks matches the container port in the common
#     case — an uncommon high port is very unlikely to be taken on the client,
#     so the forward maps localhost:PORT -> container:PORT 1:1.
# The dev server binds this port and the Mastodon OAuth callback points at it, so
# the authorization code comes back to the right place instead of a fixed :8000.
PORT_FILE="$REPO_DIR/.dev_port"
if [ -f "$PORT_FILE" ] && grep -qE '^[0-9]+$' "$PORT_FILE"; then
  DEV_PORT="$(cat "$PORT_FILE")"
else
  # 20000-32000 avoids common dev ports (3000/5000/8000/8080/5173) and the OS
  # ephemeral ranges (Linux 32768+, macOS 49152+), so it's almost always free.
  DEV_PORT="$(shuf -i 20000-32000 -n 1)"
  echo "$DEV_PORT" > "$PORT_FILE"
fi

# Keep every port-dependent setting in sync with DEV_PORT in the (gitignored) .env.
set_env_var() {
  local key="$1" value="$2"
  touch .env
  if grep -qE "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}
set_env_var MSTDN_REDIRECT_URI "http://localhost:${DEV_PORT}/mastodon_auth/"

echo "fedidevs dev server port: ${DEV_PORT} (forward localhost:${DEV_PORT} -> container:${DEV_PORT})"

PG_VER="$(ls /etc/postgresql | sort -n | tail -1)"
sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
for _ in $(seq 1 30); do
  sudo -u postgres pg_isready -q && break
  sleep 1
done

uv run python manage.py migrate --noinput
