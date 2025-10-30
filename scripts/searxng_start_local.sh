#!/usr/bin/env bash
set -euo pipefail

SEARX_DIR="/opt/searxng"
VENV_BIN="$SEARX_DIR/.venv/bin"
SETTINGS="/etc/searxng/settings.yml"
LOGFILE="/tmp/searxng.log"

mkdir -p "$(dirname "$LOGFILE")"
pkill -f 'gunicorn: master \[searx.webapp:app\]' 2>/dev/null || true
sleep 0.5 || true

/usr/bin/env -i \
  PATH="$VENV_BIN:/usr/sbin:/usr/bin:/sbin:/bin" \
  SEARXNG_SETTINGS_PATH="$SETTINGS" \
  PYTHONNOUSERSITE=1 \
  PYTHONPATH="$SEARX_DIR" \
  LC_ALL=C.UTF-8 LANG=C.UTF-8 \
  HOME=/root \
  "$VENV_BIN/python" -m gunicorn \
    --chdir "$SEARX_DIR" \
    -b 0.0.0.0:8088 \
    -w 2 \
    -k sync \
    --timeout 60 \
    --graceful-timeout 30 \
    --log-level info \
    --access-logfile - \
    --error-logfile "$LOGFILE" \
    searx.webapp:app \
    >/dev/null 2>>"$LOGFILE" &

for i in $(seq 1 30); do
  if curl -fsS --connect-timeout 1 --max-time 2 http://127.0.0.1:8088/robots.txt >/dev/null; then
    echo "[searxng] up at http://127.0.0.1:8088"
    break
  fi
  sleep 0.5
  if [ "$i" -eq 30 ]; then
    echo "[searxng] failed to start, check $LOGFILE" >&2
    exit 1
  fi
done

BACKEND_ENV="/root/consult/backend/.env"
grep -q '^SEARXNG_ENDPOINT=' "$BACKEND_ENV" 2>/dev/null \
  && sed -i 's#^SEARXNG_ENDPOINT=.*#SEARXNG_ENDPOINT=http://127.0.0.1:8088#' "$BACKEND_ENV" \
  || echo 'SEARXNG_ENDPOINT=http://127.0.0.1:8088' >> "$BACKEND_ENV"

echo "[searxng] ready and backend .env updated"
