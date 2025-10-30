#!/usr/bin/env bash
set -euo pipefail

# 停止基于源码的 SearXNG（gunicorn）

echo "[searxng] stopping ..."
pkill -f "gunicorn.*searx.webapp:app" 2>/dev/null || true
sleep 1
if ss -ltnp 2>/dev/null | grep -q ":8088 "; then
  echo "[searxng] still listening on :8088, force killing..."
  pkill -9 -f "gunicorn.*searx.webapp:app" 2>/dev/null || true
  sleep 1
fi
echo "[searxng] stopped"

