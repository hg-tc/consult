#!/usr/bin/env bash
set -euo pipefail

# 安装/更新基于源码的 SearXNG 到 /opt/searxng，并生成基础配置

SEARXNG_ROOT="/opt/searxng"
SETTINGS_DIR="/etc/searxng"
PORT="8088"

echo "[searxng] installing source build to ${SEARXNG_ROOT} ..."

apt-get update -y >/dev/null 2>&1 || true
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  git python3 python3-venv python3-pip python3-dev \
  build-essential libffi-dev libxml2-dev libxslt1-dev zlib1g-dev libjpeg-dev \
  ca-certificates >/dev/null 2>&1 || true

mkdir -p /opt
if [ ! -d "${SEARXNG_ROOT}" ]; then
  git clone --depth=1 https://github.com/searxng/searxng.git "${SEARXNG_ROOT}"
else
  git -C "${SEARXNG_ROOT}" fetch --depth=1 origin >/dev/null 2>&1 || true
  git -C "${SEARXNG_ROOT}" reset --hard origin/master >/dev/null 2>&1 || true
fi

python3 -m venv "${SEARXNG_ROOT}/.venv"
. "${SEARXNG_ROOT}/.venv/bin/activate"
python -m pip install -U pip wheel setuptools >/dev/null
pip install -r "${SEARXNG_ROOT}/requirements.txt" >/dev/null || pip install -r "${SEARXNG_ROOT}/requirements.txt" --no-build-isolation >/dev/null || true

mkdir -p "${SETTINGS_DIR}"
if [ ! -f "${SETTINGS_DIR}/settings.yml" ]; then
  cp -n "${SEARXNG_ROOT}/searx/settings.yml" "${SETTINGS_DIR}/settings.yml" || true
fi

python - <<'PY'
from pathlib import Path
import secrets, yaml
p = Path('/etc/searxng/settings.yml')
data = yaml.safe_load(p.read_text()) if p.exists() else {}
server = dict(data.get('server', {}))
server['bind_address'] = '0.0.0.0'
server['port'] = 8088
server['secret_key'] = secrets.token_hex(32)
data['server'] = server
ui = dict(data.get('ui', {}))
ui['image_proxy'] = False
data['ui'] = ui
p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
print('settings updated')
PY

echo "[searxng] install done. To start: scripts/searxng_start_local.sh"

