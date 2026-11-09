
# -*- coding: utf-8 -*-
"""长风公园—苏州河夜游路线图 v3：底图高德瓦片，路线像素级贴合河岸与园路。"""
import math, io, sys, json, urllib.request
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, ".dsh/skills/travel-guide/scripts")
from amap_route import wgs84_to_gcj02, gcj02_to_wgs84, haversine_m, uri_marker, uri_navigation, Stop

OUT = "行程/2026-11-11-长风公园-苏州河/路线图.png"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Referer": "https://www.amap.com/"}
Z, W, H, SS = 16, 1600, 1200, 2
CENTER = (121.3892, 31.2240)
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
def f(s, b=False): return ImageFont.truetype(FONT, s, index=2 if b else 0)

def merc(lon, lat, z=Z):
    n = 2 ** z * 256
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y

cx, cy = merc(*CENTER)
x0, y0 = cx - W / 2, cy - H / 2
tx0, ty0 = math.floor(x0 / 256), math.floor(y0 / 256)
tx1, ty1 = math.floor((x0 + W) / 256), math.floor((y0 + H) / 256)
ox, oy = x0 - tx0 * 256, y0 - ty0 * 256
base = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), "white")
for tx in range(tx0, tx1 + 1):
    for ty in range(ty0, ty1 + 1):
        u = f"https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={tx}&y={ty}&z={Z}"
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r:
                t = Image.open(io.BytesIO(r.read())).convert("RGB")
        except Exception:
            t = Image.new("RGB", (256, 256), "#eeeeee")
        base.paste(t, ((tx - tx0) * 256, (ty - ty0) * 256))
base = base.crop((int(ox), int(oy), int(ox) + W, int(oy) + H)).point(lambda v: int(v * 0.95 + 10))

def wgs_px(lon, lat):
    lon2, lat2 = wgs84_to_gcj02(lon, lat)
    x, y = merc(lon2, lat2)
    return (x - x0), (y - y0)

def px_wgs(x, y):
    lon = (x + x0) / (2 ** Z * 256) * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + y0) / (2 ** Z * 256)))))
    return gcj02_to_wgs84(lon, lat)

# ---- 河道中心线：扫描水体色 (174,209,252) ----
def is_water(c): return abs(c[0]-174) < 30 and abs(c[1]-209) < 25 and c[2] > 235
river_pts, prev_y = [], 890
for x in range(1130, 388, -8):
    ys = [y for y in range(int(prev_y) - 45, int(prev_y) + 45) if is_water(base.getpixel((x, y)))]
    if len(ys) >= 5:
        y = sum(ys) / len(ys); prev_y = y
        river_pts.append((x, y))
    else:
        river_pts.append((x, prev_y))

# ---- 园内环线（像素，按底图园路取点）----
park_px = [(1130, 486), (1168, 505), (1152, 546), (1206, 560), (1252, 516), (1268, 442),
           (1236, 428), (1196, 468), (1168, 505)]
conn_px = [(1168, 505), (1164, 580), (1158, 660), (1146, 740), (1130, 800), (1116, 858)]
river_line = conn_px + river_pts
river_line.append((398, 812))

ov = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
def sc(pts): return [(x * SS, y * SS) for x, y in pts]
for pts, col in [(sc(park_px), (38, 116, 78, 255)), (sc(river_line), (226, 100, 58, 255))]:
    d.line(pts, fill=(255, 255, 255, 240), width=int(5.5 * SS * 1.85), joint="curve")
    d.line(pts, fill=col, width=int(5.5 * SS), joint="curve")

GREEN, ORANGE = (38, 116, 78, 255), (226, 100, 58, 255)
def marker(xy, text, color, r=15, star=False):
    x, y = xy[0] * SS, xy[1] * SS
    d.ellipse([x - r*SS, y - r*SS, x + r*SS, y + r*SS], fill=(255, 255, 255, 255), outline=color, width=int(2.6*SS))
    if star:
        d.ellipse([x - 6.5*SS, y - 6.5*SS, x + 6.5*SS, y + 6.5*SS], fill=color)
    else:
        ft = f(15*SS, True); bb = d.textbbox((0, 0), text, font=ft)
        d.text((x-(bb[2]-bb[0])/2-bb[0], y-(bb[3]-bb[1])/2-bb[1]), text, font=ft, fill=(28, 36, 30, 255))

S = (1130, 486); G1 = (1168, 505); G2 = (1152, 546); G3 = (1206, 560); G4 = (1252, 516); G5 = (1268, 442)
P6 = (1116, 858); P7 = river_pts[len(river_pts)//2]; P8 = (398, 812)
for k, p in [("S", S), ("1", G1), ("2", G2), ("3", G3), ("4", G4), ("5", G5)]:
    marker(p, k, GREEN)
for k, p in [("6", P6), ("7", P7)]:
    marker(p, k, ORANGE)
marker(P8, "8", ORANGE, 17, star=True)


def label(xy, text, side="right", bold=True, size=19, color=(26, 34, 29, 255)):
    x, y = xy[0] * SS, xy[1] * SS
    ft = f(size*SS, bold); bb = d.textbbox((0, 0), text, font=ft)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]; pad = 22*SS
    lx = x + pad if side == "right" else x - pad - tw
    d.text((lx, y - th/2 - bb[1]), text, font=ft, fill=color, stroke_width=5*SS, stroke_fill=(255, 255, 255, 248))

label(S, "长风公园站 15 号线 · 集合", "left")
label((398, 812), "丹巴路码头 · RUN 装置（终点）", "left", size=18, color=(178, 62, 32, 255))
DX, DY = wgs_px(121.39060, 31.22460)
d.ellipse([(DX-10)*SS, (DY-10)*SS, (DX+10)*SS, (DY+10)*SS], fill=(255, 255, 255, 240), outline=(130, 130, 130, 255), width=int(2.4*SS))
label((DX, DY), "长风大悦城 5F（备选收尾）", "right", bold=False, size=16, color=(96, 96, 96, 255))


PW, PH = 470*SS, 380*SS; PX, PY = 26*SS, 26*SS
d.rounded_rectangle([PX, PY, PX+PW, PY+PH], radius=16*SS, fill=(255, 255, 255, 246), outline=(208, 213, 203, 255), width=int(1.5*SS))
d.text((PX+22*SS, PY+18*SS), "长风公园 · 苏州河 夜游", font=f(30*SS, True), fill=(24, 44, 32, 255))
d.text((PX+22*SS, PY+64*SS), "2026-11-11 周三 20:00—22:00", font=f(18*SS), fill=(66, 80, 70, 255))
d.text((PX+22*SS, PY+92*SS), "步行约 3.3 km · 慢走 2 小时", font=f(18*SS), fill=(66, 80, 70, 255))
d.line([PX+22*SS, PY+124*SS, PX+PW-22*SS, PY+124*SS], fill=(226, 230, 222, 255), width=int(1.4*SS))
items = [("S", "长风公园站（15 号线）"), ("1", "公园 4 号门 · 大渡河路"), ("2", "西老河 · 萤火栈道"),
         ("3", "银锄湖 · 临湖曲廊"), ("4", "枕流桥 · 古桥水岸"), ("5", "铁臂山 26.64m · 登顶"),
         ("6", "苏州河 · 大渡河路桥"), ("7", "半马苏河公园 · 中江路"), ("8", "丹巴路码头 · 终点")]
for i, (k, t) in enumerate(items):
    yy = PY + 140*SS + i*25*SS
    d.text((PX+24*SS, yy), k, font=f(16*SS, True), fill=GREEN if k in "S12345" else ORANGE)
    d.text((PX+52*SS, yy), t, font=f(16*SS), fill=(48, 58, 50, 255))

BX, BY, BW, BH = 26*SS, (H-126)*SS, (W-52)*SS, 100*SS
d.rounded_rectangle([BX, BY, BX+BW, BY+BH], radius=14*SS, fill=(255, 252, 246, 246), outline=(232, 220, 205, 255), width=int(1.4*SS))
d.text((BX+22*SS, BY+12*SS), "21:30 苏州河与公园景观灯关闭（11 月—次年 4 月 18:00—21:30）—— 看灯务必前压，之后只剩基础路灯", font=f(17*SS), fill=(170, 66, 38, 255))
d.text((BX+22*SS, BY+44*SS), "出发：15 号线武威东路站（5 站，约 12 分钟）｜2 号线北新泾站 2 站 → 娄山关路换 15 号线 1 站", font=f(15*SS), fill=(70, 82, 72, 255))
d.text((BX+22*SS, BY+72*SS), "底图 © 高德地图 · 路线与点位为示意，现场以路牌为准 · 生成于 2026-11-09", font=f(13*SS), fill=(150, 156, 148, 255))

out = Image.alpha_composite(base.convert("RGBA"), ov.resize((W, H), Image.LANCZOS)).convert("RGB")
out.save(OUT, quality=95)
print("saved", OUT, out.size)

# ---- 坐标与里程 ----
names = {"S": S, "1": G1, "2": G2, "3": G3, "4": G4, "5": G5, "6": P6, "7": P7, "8": P8}
wgs = {k: px_wgs(*v) for k, v in names.items()}
for k, v in wgs.items():
    print(k, "%.6f,%.6f" % (v[0], v[1]))
def path_len(seq): return sum(haversine_m(seq[i][0], seq[i][1], seq[i+1][0], seq[i+1][1]) for i in range(len(seq)-1))/1000
seqp = [px_wgs(*p) for p in park_px]; seqr = [px_wgs(*p) for p in river_line]
print("park %.2f river %.2f total %.2f" % (path_len(seqp), path_len(seqr), path_len(seqp)+path_len(seqr)))
json.dump({k: [round(v[0], 6), round(v[1], 6)] for k, v in wgs.items()}, open("行程/2026-11-11-长风公园-苏州河/素材/点位.json", "w"), ensure_ascii=False, indent=1)
