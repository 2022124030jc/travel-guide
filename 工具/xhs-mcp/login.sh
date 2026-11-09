#!/bin/bash
# 小红书扫码登录（只需一次）。登录态存在 ./.home 下，之后 start.sh 复用。
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/.home"
cd "$D"
echo "[i] 会弹出浏览器窗口显示二维码，用小红书 App 扫码"
exec env HOME="$D/.home" "$D/xiaohongshu-login" "$@"
