#!/usr/bin/env python3
"""攻略长图：JSON → HTML → Edge headless 截图 → 自动裁掉底部空白。

用法:
    python3 share_card.py spec.json -o 攻略长图.png [--html 长图.html] [--copy] [--open wechat|qq]

spec.json 结构:
{
  "title": "成都 3 日 · 吃住行全攻略",
  "subtitle": "2026-11-15 ~ 11-17 · 2 人 · 人均 1800",
  "kicker": "示例成品",
  "days": [
    {"label": "Day 1", "date": "11/15 周六", "theme": "老城与火锅",
     "stops": [{"time": "09:00", "name": "宽窄巷子", "note": "逛 1.5h，早点去人少"}]}
  ],
  "tips": ["大熊猫基地 7 点开门，11 点后熊猫睡觉"],
  "footer": "素材来源见 素材/取材.md"
}
"""
import argparse, json, os, shutil, subprocess, sys, tempfile
from html import escape

EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
BG = "#faf7f0"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:750px;background:%(bg)s;font-family:-apple-system,"Hiragino Sans GB","PingFang SC","Microsoft YaHei",sans-serif;color:#243024}
.wrap{padding:0 0 40px}
.hero{background:linear-gradient(135deg,#1f3a2b 0%%,#3c6b4a 100%%);color:#fff;padding:46px 44px 40px}
.kicker{display:inline-block;font-size:13px;letter-spacing:2px;background:rgba(255,255,255,.16);padding:5px 12px;border-radius:999px;margin-bottom:18px}
h1{font-size:38px;line-height:1.28;font-weight:700;letter-spacing:.5px}
.sub{margin-top:14px;font-size:16px;opacity:.82;line-height:1.6}
.body{padding:28px 28px 0}
.day{background:#fff;border-radius:18px;padding:24px 24px 10px;margin-bottom:18px;box-shadow:0 2px 10px rgba(30,50,35,.06)}
.dayhead{display:flex;align-items:baseline;gap:12px;border-bottom:1px dashed #e3e8e0;padding-bottom:14px;margin-bottom:6px}
.badge{background:#24402a;color:#fff;font-size:13px;font-weight:600;padding:5px 11px;border-radius:8px;letter-spacing:.5px}
.theme{font-size:20px;font-weight:700}
.date{margin-left:auto;font-size:13px;color:#7c8a7e}
.stop{display:flex;gap:14px;padding:13px 0;border-bottom:1px solid #f2f4f0}
.stop:last-child{border-bottom:none}
.time{width:56px;flex:0 0 56px;font-size:14px;color:#3c6b4a;font-weight:700;font-variant-numeric:tabular-nums;padding-top:2px}
.name{font-size:17px;font-weight:600;margin-bottom:4px}
.note{font-size:14px;color:#6b7a6e;line-height:1.55}
.tips{background:#fff8e6;border:1px solid #f0e2bd;border-radius:18px;padding:22px 24px}
.tips h3{font-size:17px;margin-bottom:12px;color:#7a5c14}
.tips li{font-size:14px;line-height:1.75;color:#5f5334;margin-left:18px}
.foot{margin:26px 28px 0;font-size:12px;color:#9aa79c;line-height:1.7;border-top:1px solid #e6ebe4;padding-top:14px}
"""


def render_html(spec):
    days = []
    for i, d in enumerate(spec.get("days", [])):
        stops = "".join(
            f'<div class="stop"><div class="time">{escape(str(s.get("time","")))}</div>'
            f'<div><div class="name">{escape(str(s.get("name","")))}</div>'
            f'<div class="note">{escape(str(s.get("note","")))}</div></div></div>'
            for s in d.get("stops", [])
        )
        days.append(
            f'<div class="day"><div class="dayhead"><div class="badge">{escape(str(d.get("label", f"Day {i+1}")))}</div>'
            f'<div class="theme">{escape(str(d.get("theme","")))}</div>'
            f'<div class="date">{escape(str(d.get("date","")))}</div></div>{stops}</div>'
        )
    tips = "".join(f"<li>{escape(str(t))}</li>" for t in spec.get("tips", []))
    tips_block = f'<div class="tips"><h3>避坑与提醒</h3><ul>{tips}</ul></div>' if tips else ""
    kicker = f'<div class="kicker">{escape(spec["kicker"])}</div>' if spec.get("kicker") else ""
    sub = f'<div class="sub">{escape(spec["subtitle"])}</div>' if spec.get("subtitle") else ""
    foot = f'<div class="foot">{escape(spec["footer"])}</div>' if spec.get("footer") else ""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{escape(spec.get('title','攻略'))}</title><style>{CSS % {'bg': BG}}</style></head><body><div class=\"wrap\">"
        f'<div class="hero">{kicker}<h1>{escape(spec.get("title",""))}</h1>{sub}</div>'
        f'<div class="body">{"".join(days)}{tips_block}</div>{foot}'
        "</div></body></html>"
    )


def shot(html_path, out_png, height):
    if not os.path.exists(EDGE):
        raise SystemExit("找不到 Microsoft Edge，改用 Pillow 兜底或手动截图")
    profile = tempfile.mkdtemp(prefix="dsh-edge-")
    cmd = [EDGE, "--headless=new", "--no-sandbox", "--disable-gpu",
           "--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check",
           "--hide-scrollbars", f"--user-data-dir={profile}",
           f"--window-size=750,{height}", "--virtual-time-budget=3000",
           f"--screenshot={out_png}", "file://" + os.path.abspath(html_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(out_png):
        raise SystemExit(f"Edge 截图失败: {r.stderr[-400:]}")


def crop_bottom(png):
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(png).convert("RGB")
    w, h = im.size
    bg = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    px = im.load()
    last = h - 1
    while last > 0:
        row = [px[x, last] for x in range(0, w, 7)]
        if any(abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) > 18 for c in row):
            break
        last -= 1
    new_h = min(h, last + 41)
    if new_h < h:
        im.crop((0, 0, w, new_h)).save(png)
        return new_h
    return h


def to_clipboard(png):
    jxa = f"""ObjC.import('AppKit');
var pb = $.NSPasteboard.generalPasteboard;
pb.clearContents;
var img = $.NSImage.alloc.initWithContentsOfFile('{png}');
pb.setDataForType(img.TIFFRepresentation, $.NSPasteboardTypeTIFF);
"""
    subprocess.run(["osascript", "-l", "JavaScript", "-e", jxa], check=True)


def main():
    ap = argparse.ArgumentParser(description="攻略长图生成（Edge headless）")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", default="攻略长图.png")
    ap.add_argument("--html", default=None)
    ap.add_argument("--height", type=int, default=6000, help="截图初始高度，之后自动裁切")
    ap.add_argument("--copy", action="store_true", help="生成后把图片放进剪贴板")
    ap.add_argument("--open", dest="open_app", choices=["wechat", "qq"], help="生成后唤起 App")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    html_path = args.html or os.path.splitext(args.out)[0] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(spec))
    shot(html_path, args.out, args.height)
    h = crop_bottom(args.out)
    from PIL import Image
    w, hh = Image.open(args.out).size
    print(f"[ok] {args.out}  {w}x{hh}  ({h or hh})")
    if args.copy:
        to_clipboard(os.path.abspath(args.out))
        print("[clipboard] 图片已复制，去聊天窗口 Cmd+V")
    if args.open_app:
        subprocess.run(["open", "-a", "WeChat" if args.open_app == "wechat" else "QQ"])
        print(f"[open] 已唤起 {args.open_app}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
