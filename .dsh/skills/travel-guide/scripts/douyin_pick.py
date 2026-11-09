#!/usr/bin/env python3
"""抖音攻略取材：抓 /shipin/<id> SEO 落地页，抽出标题 + AI 文稿（ASR）。

零依赖（仅标准库）。匿名可取，robots 允许。
用法:
    python3 douyin_pick.py <url|video_id> [<url2> ...] [-o out.json] [--md out.md]

输出 JSON: {url, video_id, fetched_at, publish_time, author, items:[{title, duration, transcript}]}
"""
import argparse, json, re, sys, time, html as htmllib
import urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def video_id(s):
    s = s.strip()
    m = re.search(r"/shipin/(\d+)", s) or re.search(r"/video/(\d+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{10,25}", s):
        return s
    raise SystemExit(f"无法识别视频 id: {s!r}（需要 /shipin/<id> 链接或纯数字 id）")


def fetch(url, retries=2):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    last = None
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + i * 3)
    raise SystemExit(f"抓取失败 {url}: {last}")


def visible_lines(raw):
    t = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"</(p|div|h\d|li|span|a)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmllib.unescape(t)
    lines = [re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n")]
    return [x for x in lines if x]


DUR = re.compile(r"^\d{2}:\d{2}$")
TAG = re.compile(r"^#[^\s]")


def parse(raw):
    lines = visible_lines(raw)
    items, cur, pending_ai = [], None, False
    publish = author = None
    for i, line in enumerate(lines):
        if publish is None:
            m = re.search(r"发布时间[:：]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", line)
            if m:
                publish = m.group(1)
                if i + 1 < len(lines):
                    nxt = lines[i + 1]
                    noise = {"查看AI文稿", "AI文稿", "展开", "关注", "举报"}
                    if (nxt not in noise and not TAG.match(nxt) and len(nxt) < 30
                            and not re.fullmatch(r"[\d.万+]+", nxt)):
                        author = nxt
                continue
        if DUR.match(line) and i + 1 < len(lines):
            nxt = lines[i + 1]
            if len(nxt) >= 4 and not TAG.match(nxt):
                title = nxt.split("#")[0].strip() or nxt
                cur = {"duration": line, "title": title, "transcript": ""}
                items.append(cur)
                pending_ai = False
                continue
        if line == "AI文稿" or line == "查看AI文稿":
            pending_ai = True
            continue
        if pending_ai and cur is not None and not cur["transcript"] and len(line) > 30:
            cur["transcript"] = line
            pending_ai = False
    # 页面里 AI 文稿也可能以 <p data-e2e="ai-text"> 出现，作为兜底补全
    ai_raw = re.findall(r'<p[^>]*data-e2e="ai-text"[^>]*>(.*?)</p>', raw, re.S)
    ai_texts = [htmllib.unescape(re.sub(r"<[^>]+>", "", a)).strip() for a in ai_raw]
    ai_texts = [a for a in ai_texts if len(a) > 30]
    for a in ai_texts:
        if not any(a[:40] == it["transcript"][:40] for it in items if it["transcript"]):
            items.append({"duration": "", "title": "", "transcript": a})
    for it in items:
        if it["transcript"] and "AI文稿" in it["transcript"]:
            it["transcript"] = it["transcript"].split("AI文稿", 1)[-1].strip()
    items = [it for it in items if it["transcript"] or it["title"]]
    return lines, items, publish, author


def main():
    ap = argparse.ArgumentParser(description="抖音 /shipin 攻略取材（零依赖）")
    ap.add_argument("targets", nargs="+", help="视频链接或 id")
    ap.add_argument("-o", "--out", help="JSON 输出路径")
    ap.add_argument("--md", help="Markdown 摘要输出路径")
    ap.add_argument("--gap", type=float, default=3.0, help="多次抓取间隔秒数（默认 3）")
    args = ap.parse_args()

    out = {"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "videos": []}
    for n, tgt in enumerate(args.targets):
        vid = video_id(tgt)
        url = f"https://www.douyin.com/shipin/{vid}"
        raw = fetch(url)
        if len(raw) < 20000:
            print(f"[warn] {vid} 页面过小（{len(raw)}B），可能已下线或改版", file=sys.stderr)
        lines, items, publish, author = parse(raw)
        rec = {"url": url, "video_id": vid, "publish_time": publish, "author": author,
               "items": items, "page_lines": len(lines)}
        out["videos"].append(rec)
        n_ai = sum(1 for it in items if it["transcript"])
        print(f"[ok] {vid}: {len(items)} 条, {n_ai} 段 AI 文稿, 发布 {publish or '未知'}, 作者 {author or '未知'}")
        if n < len(args.targets) - 1:
            time.sleep(args.gap)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[saved] {args.out}")
    if args.md:
        buf = [f"# 抖音取材 · {out['fetched_at']}\n"]
        for v in out["videos"]:
            buf.append(f"## {v['url']}\n")
            buf.append(f"- 发布时间：{v['publish_time'] or '未知'}\n- 作者：{v['author'] or '未知'}\n")
            for it in v["items"]:
                buf.append(f"### {it['title'] or '（无标题）'} {it['duration']}\n")
                if it["transcript"]:
                    buf.append(f"> {it['transcript']}\n")
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(buf))
        print(f"[saved] {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
