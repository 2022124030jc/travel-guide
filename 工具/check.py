#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check.py — 仓库自检，本地直接跑（接 CI 时也跑它）。

检查项：
  1. Python 语法：所有 .py 都能被 ast.parse
  2. JSON 可解析：所有 .json 都是合法 JSON
  3. 本机链接：Markdown 正文里的相对链接 / 图片都能在仓库里找到（代码块里的示例不算）
  4. 技能元数据：.dsh/skills/*/SKILL.md 带 name 与 description frontmatter
  5. 脚本冒烟：零 Key 跑一遍 amap_route.py 内置样例，产物存在且可解析
  6. 疑似密钥：token / 私钥 / 带凭据的 GitHub URL 不得入库

只查仓库里已跟踪的文件（git ls-files），tmp/、登录态与二进制不在范围内。

用法：
    python3 工具/check.py          # 全部检查
    python3 工具/check.py -v       # 逐项打印通过的检查

退出码 = 失败项数（0 表示通过），与 plan_lint.py 的口径一致。
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "tmp", ".dsh-backup", "node_modules", "__pycache__",
             ".home", ".rod-data", "edge-prof"}
TEXT_EXT = {".py", ".md", ".json", ".yml", ".yaml", ".sh", ".txt", ".html", ".css"}
MAX_SCAN_BYTES = 2 * 1024 * 1024

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\n]+)\)")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{30,}")),
    ("私钥", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("带凭据的 GitHub URL", re.compile(r"https://[^\s:/@]+:[A-Za-z0-9]{30,}@github\.com")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("OpenAI 风格 key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
]


def repo_files():
    """已跟踪文件列表；没有 git（如 tarball 解压）时退化为目录遍历。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True, check=True, timeout=30,
        )
        names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
        if names:
            return sorted(Path(n) for n in names if (ROOT / n).exists())
    except (OSError, subprocess.SubprocessError):
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            files.append(Path(dirpath, name).relative_to(ROOT))
    return sorted(files)


def read_text(path):
    return path.read_text(encoding="utf-8")


def check_python(files, fail, ok):
    count = 0
    for rel in files:
        if rel.suffix != ".py":
            continue
        count += 1
        try:
            ast.parse(read_text(ROOT / rel))
        except SyntaxError as exc:
            fail.append(f"Python 语法错误 {rel}:{exc.lineno}: {exc.msg}")
        except (UnicodeDecodeError, OSError) as exc:
            fail.append(f"Python 文件读不出来 {rel}: {exc}")
    ok.append(f"Python 语法 {count} 个文件")


def check_json(files, fail, ok):
    count = 0
    for rel in files:
        if rel.suffix != ".json":
            continue
        count += 1
        try:
            json.loads(read_text(ROOT / rel))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            fail.append(f"JSON 解析失败 {rel}: {exc}")
    ok.append(f"JSON {count} 个文件")


def check_links(files, fail, ok):
    count = 0
    for rel in files:
        if rel.suffix != ".md":
            continue
        try:
            text = read_text(ROOT / rel)
        except (UnicodeDecodeError, OSError) as exc:
            fail.append(f"Markdown 读不出来 {rel}: {exc}")
            continue
        text = INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip()
            if target.startswith("<") and ">" in target:
                target = target[1:target.index(">")]
            parts = target.split()
            target = parts[0] if parts else ""
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            clean = urllib.parse.unquote(target.split("#")[0].split("?")[0])
            if not clean:
                continue
            count += 1
            if not (ROOT / rel).parent.joinpath(clean).exists():
                fail.append(f"链接失效 {rel} → {target}")
    ok.append(f"Markdown 相对链接 {count} 条")


def check_skills(files, fail, ok):
    count = 0
    for rel in files:
        if rel.name != "SKILL.md":
            continue
        count += 1
        try:
            text = read_text(ROOT / rel)
        except (UnicodeDecodeError, OSError) as exc:
            fail.append(f"SKILL.md 读不出来 {rel}: {exc}")
            continue
        if not text.startswith("---"):
            fail.append(f"SKILL.md 缺少 frontmatter：{rel}")
            continue
        head = text.split("---", 2)[1] if text.count("---") >= 2 else ""
        for field in ("name:", "description:"):
            if field not in head:
                fail.append(f"SKILL.md frontmatter 缺 {field} {rel}")
    ok.append(f"技能 frontmatter {count} 个")


def check_route_smoke(fail, ok):
    script = ROOT / ".dsh/skills/travel-guide/scripts/amap_route.py"
    if not script.exists():
        fail.append(f"冒烟脚本不存在：{script.relative_to(ROOT)}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        cmd = [sys.executable, str(script),
               "--out", str(out / "route.svg"),
               "--html", str(out / "route.html"),
               "--links", str(out / "links.json"),
               "--title", "自检样例"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            fail.append(f"amap_route.py 冒烟没跑起来：{exc}")
            return
        if proc.returncode != 0:
            fail.append(f"amap_route.py 冒烟失败 [exit {proc.returncode}]：{proc.stderr.strip()[:300]}")
            return
        for name in ("route.svg", "route.html", "links.json"):
            path = out / name
            if not path.exists() or path.stat().st_size == 0:
                fail.append(f"冒烟产物缺失或为空：{name}")
        try:
            links = json.loads((out / "links.json").read_text(encoding="utf-8"))
            if not links:
                fail.append("冒烟产物 links.json 为空")
        except (json.JSONDecodeError, OSError) as exc:
            fail.append(f"冒烟产物 links.json 解析失败：{exc}")
        html_path = out / "route.html"
        html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        if "自检样例" not in html:
            fail.append("冒烟产出的 HTML 里没有标题")
        svg_path = out / "route.svg"
        if not svg_path.exists() or not svg_path.read_text(encoding="utf-8").lstrip().startswith("<"):
            fail.append("冒烟产出的 SVG 不像 SVG")
    ok.append("amap_route.py 零 Key 冒烟")


def check_secrets(files, fail, ok):
    count = 0
    for rel in files:
        if rel.suffix.lower() not in TEXT_EXT:
            continue
        path = ROOT / rel
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = read_text(path)
        except (OSError, UnicodeDecodeError):
            continue
        count += 1
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                fail.append(f"疑似{label}提交进了仓库：{rel}")
    ok.append(f"密钥扫描 {count} 个文本文件")


def main():
    parser = argparse.ArgumentParser(description="travel-guide 仓库自检")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印通过的检查项")
    args = parser.parse_args()

    files = repo_files()
    fail, ok = [], []
    check_python(files, fail, ok)
    check_json(files, fail, ok)
    check_links(files, fail, ok)
    check_skills(files, fail, ok)
    check_route_smoke(fail, ok)
    check_secrets(files, fail, ok)

    print(f"检查了 {len(files)} 个已跟踪文件")
    for line in ok:
        if args.verbose:
            print(f"  ok  {line}")
    for line in fail:
        print(f"  FAIL {line}")
    if fail:
        print(f"自检未通过：{len(fail)} 项失败")
        return len(fail)
    print("自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
