#!/usr/bin/env bash
# 兼容 /bin/sh 调用：不强依赖 pipefail
set -eu
if (set -o | grep -q pipefail) 2>/dev/null; then
  set -o pipefail
fi

# 解析脚本所在目录（兼容 /bin/sh）
SCRIPT_PATH="$0"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd)

SEARXNG_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../docker/searxng" >/dev/null 2>&1 && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)
BACKEND_ENV_FILE="$ROOT_DIR/backend/.env"
ENDPOINT_DEFAULT="http://localhost:8080"

echo "[searxng] using directory: $SEARXNG_DIR"

# 检查 docker 是否可用
if ! command -v docker >/dev/null 2>&1; then
  echo "[searxng] ERROR: docker 未安装或不可用。请先安装 Docker 再运行本脚本。"
  echo "[searxng] 参考安装（Debian/Ubuntu）："
  echo "  sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg"
  echo "  sudo install -m 0755 -d /etc/apt/keyrings"
  echo "  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
  echo "  echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \"\$(. /etc/os-release && echo \$VERSION_CODENAME)\" stable\" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null"
  echo "  sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
  echo "安装后执行： sudo usermod -aG docker \"$USER\" && newgrp docker"
  exit 127
fi

cd "$SEARXNG_DIR"
echo "[searxng] starting docker compose..."
docker compose up -d

echo "[searxng] waiting for endpoint to be ready at $ENDPOINT_DEFAULT ..."
RETRY=30
until curl -fsS "$ENDPOINT_DEFAULT" >/dev/null 2>&1; do
  RETRY=$((RETRY-1)) || true
  if [ "$RETRY" -le 0 ]; then
    echo "[searxng] ERROR: endpoint not ready after waiting. Please check docker logs."
    exit 1
  fi
  sleep 1
done

echo "[searxng] endpoint is up: $ENDPOINT_DEFAULT"

mkdir -p "$(dirname "$BACKEND_ENV_FILE")"
touch "$BACKEND_ENV_FILE"

# update or append SEARXNG_ENDPOINT in backend/.env
if grep -qE '^SEARXNG_ENDPOINT=' "$BACKEND_ENV_FILE"; then
  sed -i.bak "s#^SEARXNG_ENDPOINT=.*#SEARXNG_ENDPOINT=$ENDPOINT_DEFAULT#g" "$BACKEND_ENV_FILE"
else
  echo "SEARXNG_ENDPOINT=$ENDPOINT_DEFAULT" >> "$BACKEND_ENV_FILE"
fi

echo "[searxng] wrote SEARXNG_ENDPOINT to $BACKEND_ENV_FILE"
echo "[searxng] done."


