#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_client.py —— 极简 MCP Streamable-HTTP 客户端（只用标准库）。

给 xiaohongshu-mcp 用：initialize → tools/list → tools/call。
用法:
    python3 mcp_client.py list
    python3 mcp_client.py call <tool> '<json-args>'
"""
import json
import sys
import urllib.request

ENDPOINT = "http://127.0.0.1:18060/mcp"


class MCP:
    def __init__(self, url=ENDPOINT):
        self.url = url
        self.session_id = None
        self._id = 0

    def _post(self, payload):
        data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "travel-guide/1.0",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            raw = resp.read().decode("utf-8", "replace")
        return self._decode(raw)

    @staticmethod
    def _decode(raw):
        raw = raw.strip()
        if not raw:
            return None
        if raw.startswith("{"):
            return json.loads(raw)
        # SSE: 逐行取 data:
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk.startswith("{"):
                    return json.loads(chunk)
        raise RuntimeError(f"无法解析响应: {raw[:200]}")

    def rpc(self, method, params=None, notify=False):
        self._id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if not notify:
            payload["id"] = self._id
        if params is not None:
            payload["params"] = params
        return self._post(payload)

    def initialize(self):
        r = self.rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "travel-guide", "version": "1.0"},
        })
        self.rpc("notifications/initialized", None, notify=True)
        return r

    def list_tools(self):
        r = self.rpc("tools/list", {})
        return r["result"]["tools"]

    def call(self, name, args=None):
        return self.rpc("tools/call", {"name": name, "arguments": args or {}})


def main(argv):
    cli = MCP()
    cli.initialize()
    if len(argv) < 2 or argv[1] == "list":
        for t in cli.list_tools():
            print(f"- {t['name']}: {(t.get('description') or '')[:100]}")
        return 0
    if argv[1] == "call":
        args = json.loads(argv[3]) if len(argv) > 3 else {}
        r = cli.call(argv[2], args)
        print(json.dumps(r, ensure_ascii=False, indent=2)[:6000])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
