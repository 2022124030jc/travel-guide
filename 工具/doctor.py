#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py —— 攻略取材链路自检：抖音 / 小红书 / 高德 / OSRM 四条腿逐个探活。

用法：python3 工具/doctor.py
"""
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def http(url, timeout=8, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 travel-guide"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def check_douyin():
    url = "https://www.douyin.com/shipin/7373860356739090473"
    try:
        _, body = http(url, timeout=20)
        n = len(body)
        return ("OK", f"{n/1024:.0f} KB，{'含 AI 文稿' if b'AI' in body or 'AI'.encode() in body else '结构待查'}") if n > 20000 \
            else ("WARN", f"页面过小 {n}B，可能改版")
    except Exception as e:  # noqa: BLE001
        return "FAIL", str(e)[:80]


def check_osrm():
    url = ("https://router.project-osrm.org/route/v1/driving/"
           "104.059,30.669;104.081,30.653?overview=false")
    try:
        _, body = http(url, timeout=12)
        d = json.loads(body)
        if d.get("code") != "Ok":
            return "WARN", f"code={d.get('code')}"
        r = d["routes"][0]
        return "OK", f"{r['distance']/1000:.1f} km / {r['duration']/60:.0f} min"
    except Exception as e:  # noqa: BLE001
        return "FAIL", str(e)[:80]


def _amap_key():
    env = os.environ.get("AMAP_MAPS_API_KEY", "").strip()
    if env:
        return env, "env"
    home = Path.home()
    for p in (home / ".dsh/amap/key", home / ".dsh/amap/credentials.json"):
        try:
            if p.is_file():
                if p.suffix == ".json":
                    k = json.loads(p.read_text()).get("amap_key", "")
                else:
                    k = p.read_text().strip()
                if k:
                    return k, str(p)
        except Exception:  # noqa: BLE001
            pass
    return "", ""


def check_amap():
    key, where = _amap_key()
    if not key:
        return "NOKEY", "未配置（存 ~/.dsh/amap/key 或设 AMAP_MAPS_API_KEY）"
    try:
        _, body = http(f"https://restapi.amap.com/v3/ip?key={key}", timeout=10)
        d = json.loads(body)
        if d.get("status") == "1":
            return "OK", f"来源 {where}，IP 定位 {d.get('province', '')}{d.get('city', '')}"
        return "FAIL", f"{d.get('info')} ({d.get('infocode')})"
    except Exception as e:  # noqa: BLE001
        return "FAIL", str(e)[:80]


def check_xhs():
    try:
        with socket.create_connection(("127.0.0.1", 18060), timeout=3):
            pass
    except Exception:  # noqa: BLE001
        cache = ROOT / "工具/xhs-mcp/.home/Library/Caches/xiaohongshu-mcp"
        size = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) if cache.exists() else 0
        if size > 50 * 1024 * 1024:
            return "READY", f"浏览器已就绪（{size/1e6:.0f} MB），服务未启动：跑 工具/xhs-mcp/start.sh"
        return "WAIT", f"浏览器下载中（{size/1e6:.0f} MB / ~150 MB）"
    # 服务在跑，进一步确认登录态
    try:
        sys.path.insert(0, str(ROOT / "工具/xhs-mcp"))
        from mcp_client import MCP  # noqa: PLC0415
        cli = MCP()
        cli.initialize()
        r = cli.call("check_login_status")
        text = "".join(p.get("text", "") for p in r["result"]["content"])
        if "未登录" in text:
            return "LOGIN", "服务在跑，但未登录：跑 工具/xhs-mcp/login.sh 扫码"
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        return "OK", f"服务 + 登录正常（{first.strip()}）"
    except Exception as exc:  # noqa: BLE001
        return "WARN", f"服务在跑但探测失败：{str(exc)[:60]}"


def main():
    rows = [("抖音 /shipin", *check_douyin()),
            ("小红书 MCP", *check_xhs()),
            ("高德 API", *check_amap()),
            ("OSRM 路网", *check_osrm())]
    width = max(len(r[0]) for r in rows)
    print(f"{'能力'.ljust(width)}  状态    说明")
    print("-" * (width + 40))
    for name, status, detail in rows:
        print(f"{name.ljust(width)}  {status.ljust(7)} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
