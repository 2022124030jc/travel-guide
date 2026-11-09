#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书攻略取材：关键词搜索 → 取前 N 篇 → 抓正文与评论 → JSON/Markdown。

依赖本地已启动的 xiaohongshu-mcp（http://127.0.0.1:18060）和一次扫码登录。
零第三方依赖，只用标准库。

用法:
    python3 xhs_pick.py --keyword "成都三日游" --limit 3 -o 素材/xhs.json --md 素材/xhs.md
    python3 xhs_pick.py --keyword "成都三日游" --keyword "成都避坑" --limit 5 --comments
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ENDPOINT = "http://127.0.0.1:18060/mcp"


class MCP:
    def __init__(self, url=ENDPOINT):
        self.url, self.session_id, self._id = url, None, 0

    def _post(self, payload):
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            raw = resp.read().decode("utf-8", "replace")
        raw = raw.strip()
        if not raw:
            return None
        if raw.startswith("{"):
            return json.loads(raw)
        for line in raw.splitlines():
            if line.strip().startswith("data:"):
                chunk = line.strip()[5:].strip()
                if chunk.startswith("{"):
                    return json.loads(chunk)
        raise RuntimeError(f"无法解析 MCP 响应: {raw[:200]}")

    def rpc(self, method, params=None, notify=False):
        self._id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if not notify:
            payload["id"] = self._id
        if params is not None:
            payload["params"] = params
        return self._post(payload)

    def init(self):
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "travel-guide", "version": "1.0"}})
        self.rpc("notifications/initialized", None, notify=True)

    def call(self, name, args=None):
        r = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        if "error" in r:
            raise RuntimeError(r["error"])
        content = r.get("result", {}).get("content", [])
        text = "".join(part.get("text", "") for part in content if part.get("type") == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}


def _num(v):
    try:
        return int(str(v).replace("万", "0000").replace("+", ""))
    except (TypeError, ValueError):
        return 0


def search(cli, keyword, limit, filters=None):
    data = cli.call("search_feeds", {"keyword": keyword, "filters": filters or {}})
    feeds = (data or {}).get("feeds", []) or []
    out = []
    for f in feeds:
        card = f.get("noteCard") or {}
        info = card.get("interactInfo") or {}
        title = card.get("displayTitle") or ""
        if not title:
            continue
        out.append({
            "id": f.get("id"),
            "xsec_token": f.get("xsecToken"),
            "title": title,
            "author": (card.get("user") or {}).get("nickname", ""),
            "likes": _num(info.get("likedCount")),
            "likes_raw": info.get("likedCount", ""),
            "collects_raw": info.get("collectedCount", ""),
            "comments_raw": info.get("commentCount", ""),
            "url": f"https://www.xiaohongshu.com/explore/{f.get('id')}?xsec_token={f.get('xsecToken')}&xsec_source=pc_search",
            "keyword": keyword,
        })
    out.sort(key=lambda x: x["likes"], reverse=True)
    return out[:limit]


def detail(cli, item, with_comments=False):
    args = {"feed_id": item["id"], "xsec_token": item["xsec_token"]}
    if with_comments:
        args.update({"load_all_comments": True, "limit": 20, "click_more_replies": True})
    data = cli.call("get_feed_detail", args)
    note = ((data or {}).get("data") or {}).get("note") or {}
    item["desc"] = (note.get("desc") or "").strip()
    item["publish_time"] = (datetime.fromtimestamp(note["time"] / 1000).strftime("%Y-%m-%d")
                            if note.get("time") else "")
    comments = ((data or {}).get("data") or {}).get("comments") or []
    if isinstance(comments, dict):
        comments = comments.get("list") or []
    item["comments"] = [{"user": (c.get("userInfo") or c.get("user") or {}).get("nickname", ""),
                         "text": (c.get("content") or "").strip()}
                        for c in comments[:12] if (c.get("content") or "").strip()]
    return item


def main():
    ap = argparse.ArgumentParser(description="小红书攻略取材（走本地 xiaohongshu-mcp）")
    ap.add_argument("--keyword", action="append", required=True, help="搜索关键词，可重复")
    ap.add_argument("--limit", type=int, default=3, help="每个关键词取几篇（默认 3）")
    ap.add_argument("--comments", action="store_true", help="额外抓评论（避坑点常在评论）")
    ap.add_argument("--gap", type=float, default=3.0, help="篇间间隔秒数（默认 3）")
    ap.add_argument("-o", "--out", help="JSON 输出路径")
    ap.add_argument("--md", help="Markdown 输出路径")
    args = ap.parse_args()

    cli = MCP()
    cli.init()
    status = "".join(part.get("text", "") for part in
                     cli.rpc("tools/call", {"name": "check_login_status", "arguments": {}})
                     .get("result", {}).get("content", []))
    if "未登录" in status:
        sys.exit("小红书未登录：先运行 工具/xhs-mcp/login.sh 扫码，再运行 start.sh")

    items = []
    for kw in args.keyword:
        found = search(cli, kw, args.limit)
        print(f"[search] {kw}: {len(found)} 篇")
        for it in found:
            try:
                detail(cli, it, args.comments)
                print(f"  [ok] {it['title'][:34]}  {len(it['desc'])} 字  ♥{it['likes_raw']}")
            except Exception as exc:  # noqa: BLE001
                it.setdefault("desc", "")
                print(f"  [warn] {it['title'][:34]}: {exc}", file=sys.stderr)
            items.append(it)
            time.sleep(args.gap)

    payload = {"fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "keywords": args.keyword, "items": items}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {args.out}")
    if args.md:
        buf = [f"# 小红书取材 · {payload['fetched_at']}", ""]
        for it in items:
            buf += [f"## {it['title']}", "",
                    f"- 作者：{it['author']} ｜ 赞 {it['likes_raw']} 收藏 {it['collects_raw']} 评论 {it['comments_raw']}",
                    f"- 发布：{it.get('publish_time') or '未知'} ｜ [原帖]({it['url']})", "",
                    it.get("desc", ""), ""]
            if it.get("comments"):
                buf.append("**评论摘录**")
                buf += [f"- {c['user']}：{c['text']}" for c in it["comments"]]
                buf.append("")
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text("\n".join(buf), encoding="utf-8")
        print(f"[saved] {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
