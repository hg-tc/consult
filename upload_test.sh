#!/usr/bin/env bash
set -euo pipefail

# 直连后端的地址（请按需修改端口/路径）
BACKEND_URL="http://127.0.0.1:18000/api/global/documents/upload"

# 生成 200MB 测试文件（优先使用 fallocate，失败则回退到 dd）
TEST_FILE="test_200mb.bin"
if [ ! -f "$TEST_FILE" ]; then
  if command -v fallocate >/dev/null 2>&1; then
    echo "Generating 200MB file with fallocate..."
    fallocate -l 200M "$TEST_FILE"
  else
    echo "Generating 200MB file with dd..."
    dd if=/dev/zero of="$TEST_FILE" bs=1M count=200 status=progress
  fi
fi

echo "Uploading to $BACKEND_URL"
# 关键点：
# -H 'Expect:' 去掉 Expect: 100-continue，避免某些代理/服务器握手问题
# --max-time 1200 防止超时（20分钟）
# -w 输出详细时延统计，便于定位卡在“上传”还是“读取响应”
# -v 打印请求/响应头
curl -v \
  -H 'Expect:' \
  --max-time 1200 \
  -w "\n\n--- curl timing ---\nnamelookup:  %{time_namelookup}s\nconnect:     %{time_connect}s\nappconnect:  %{time_appconnect}s\npretransfer: %{time_pretransfer}s\nstarttransfer:%{time_starttransfer}s\ntotal:       %{time_total}s\nsize_upload: %{size_upload} bytes\nspeed_upload:%{speed_upload} bytes/s\n\nHTTP %{http_code}\n" \
  -F "file=@${TEST_FILE};type=application/octet-stream" \
  "$BACKEND_URL"

echo "Done."