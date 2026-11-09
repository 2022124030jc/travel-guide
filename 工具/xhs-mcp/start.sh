#!/bin/bash
# 启动小红书 MCP 服务（默认 http://127.0.0.1:18060）。
# 首次运行会下载内置浏览器（~150MB），之后秒起。
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/.home"
cd "$D"
exec env HOME="$D/.home" COOKIES_PATH="$D/cookies.json" \
  "$D/xiaohongshu-mcp" -headless -port "${PORT:-:18060}" "$@"
