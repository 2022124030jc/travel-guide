#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
amap_route_demo.py —— 零 Key / 零依赖 的高德路线图生成器

用途
----
在不申请高德 API Key、不联网、不安装任何第三方包的前提下，把一串
经纬度点位（GCJ-02 高德坐标）画成一张路线示意图（SVG），并同时生成
可直接分享到微信/浏览器的高德 URI 链接与 ditu.amap.com 网页路线链接。
用于「攻略」类文档：把文字行程变成一张能插进 Markdown 的路线图。

三种输出
--------
1. SVG 静态路线图   —— 纯本地绘制，可嵌入 Markdown / 直接双击用浏览器打开
2. 高德 URI 链接    —— uri.amap.com/marker|navigation，无需 Key，手机上打开
3. 网页版路线链接    —— ditu.amap.com/dir?...，无需 Key，PC 上打开

依赖：仅 Python 标准库（3.8+）。
坐标系：输入默认 GCJ-02（高德/腾讯/微信用的火星坐标系）。
        若坐标来自 GPS 轨迹或 OSM，请加 --from-wgs84 让脚本自动转换，
        或在代码里调用 wgs84_to_gcj02()。

示例
----
    python3 amap_route_demo.py --out ../../../../行程/_demo_route.svg
    python3 amap_route_demo.py --out route.svg --html route.html --links links.json
    python3 amap_route_demo.py --from-json my_route.json --out route.svg
    python3 amap_route_demo.py --from-wgs84 --out route.svg   # 输入是 GPS 原始坐标
    python3 amap_route_demo.py --mode bus --out route.svg

JSON 输入格式（--from-json）：
    {"title": "北京二日游", "stops": [
        {"name": "天安门广场", "lon": 116.397128, "lat": 39.916527},
        ...
    ]}
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 0. 常量
# --------------------------------------------------------------------------

URI_BASE = "https://uri.amap.com"
SRC = "dsh-travel-guide"          # 高德文档建议填「使用方来源信息」
MAX_MARKERS = 10                  # uri.amap.com/marker 的 markers 上限
MODES = ("car", "bus", "walk", "ride")
DISTORT_MAX = 2.2                 # 横纵允许的最大不等比拉伸（示意图专用）
M_PER_DEG = 111320.0

# 配色（浅色、适合打印/嵌入文章）
C_BG_TOP = "#fbfdff"
C_BG_BOTTOM = "#eef3fa"
C_GRID = "#dfe7f2"
C_ROUTE = "#1677ff"
C_ROUTE_HALO = "#1677ff"
C_START = "#12b76a"
C_END = "#f04438"
C_POI = "#1677ff"
C_TEXT = "#1b2430"
C_MUTED = "#6b7a90"
FONT = ("'PingFang SC','Hiragino Sans GB','Microsoft YaHei',"
        "'Noto Sans CJK SC',sans-serif")


# --------------------------------------------------------------------------
# 1. 坐标系转换：WGS-84 <-> GCJ-02 <-> BD-09
#    高德 / 腾讯 / 微信内置地图 = GCJ-02（火星坐标，国测局加密）
#    GPS / OSM / 谷歌地球 / 多数国际数据 = WGS-84
#    百度 = BD-09
# --------------------------------------------------------------------------

_A = 6378245.0                 # 克拉索夫斯基椭球长半轴
_EE = 0.00669342162296594323   # 第一偏心率平方


def out_of_china(lon: float, lat: float) -> bool:
    """粗略判断是否在中国境外（境外不做偏移）。"""
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lon: float, lat: float, ndigits: int = 6) -> Tuple[float, float]:
    """GPS 原始坐标 -> 高德/火星坐标。国内偏移通常 300~800m。"""
    if out_of_china(lon, lat):
        return (round(lon, ndigits), round(lat, ndigits))
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return (round(lon + dlon, ndigits), round(lat + dlat, ndigits))


def gcj02_to_wgs84(lon: float, lat: float, ndigits: int = 6) -> Tuple[float, float]:
    """高德坐标 -> GPS 原始坐标（迭代反解，3 次≈0.1m）。"""
    if out_of_china(lon, lat):
        return (round(lon, ndigits), round(lat, ndigits))
    wlon, wlat = lon, lat
    for _ in range(3):
        glon, glat = wgs84_to_gcj02(wlon, wlat, ndigits=12)
        wlon += lon - glon
        wlat += lat - glat
    return (round(wlon, ndigits), round(wlat, ndigits))


def bd09_to_gcj02(bd_lon: float, bd_lat: float, ndigits: int = 6) -> Tuple[float, float]:
    """百度坐标 -> 高德坐标。"""
    x_pi = math.pi * 3000.0 / 180.0
    x, y = bd_lon - 0.0065, bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return (round(z * math.cos(theta), ndigits), round(z * math.sin(theta), ndigits))


def gcj02_to_bd09(gcj_lon: float, gcj_lat: float, ndigits: int = 6) -> Tuple[float, float]:
    """高德坐标 -> 百度坐标。"""
    x_pi = math.pi * 3000.0 / 180.0
    z = math.sqrt(gcj_lon * gcj_lon + gcj_lat * gcj_lat) + 0.00002 * math.sin(gcj_lat * x_pi)
    theta = math.atan2(gcj_lat, gcj_lon) + 0.000003 * math.cos(gcj_lon * x_pi)
    return (round(z * math.cos(theta) + 0.0065, ndigits), round(z * math.sin(theta) + 0.006, ndigits))


# --------------------------------------------------------------------------
# 2. 距离与几何
# --------------------------------------------------------------------------

_EARTH_R = 6371008.8


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """球面直线距离（米）。对 GCJ-02 坐标误差 < 0.5%，画示意图够用。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def fmt_distance(m: float) -> str:
    return f"{m / 1000:.1f} km" if m >= 1000 else f"{m:.0f} m"


def fmt_duration(seconds: float, estimate: bool = False) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes >= 60:
        text = f"{minutes // 60} 小时 {minutes % 60} 分"
    else:
        text = f"{minutes} 分钟"
    return ("约 " + text) if estimate else text


# --------------------------------------------------------------------------
# 1b. 无 Key 的真实里程/耗时：OSRM 公共路由（OpenStreetMap 数据）
#     高德 Web 服务要 Key，OSRM 不要；用 OSM 路网算出"真走了多远、大概多久"。
# --------------------------------------------------------------------------

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"
SPEED_KMH = {"bus": 16.0, "walk": 4.5, "ride": 15.0}   # car 用 OSRM 返回的时长


def osrm_live(stops: Sequence["Stop"], mode: str = "car",
              timeout: float = 15.0) -> Optional[dict]:
    """用 OSRM 公共实例算真实路程与耗时。

    输入是 GCJ-02（高德）坐标，OSRM 要 WGS-84，必须先转换，否则整条线偏 500 米。
    非驾车模式：路程仍用同一张路网（近似），时间按该方式平均速度估算，
    返回里标 time_is_estimate，渲染时会带「约」字。
    失败返回 None，调用方回落到直线距离。
    """
    if len(stops) < 2:
        return None
    coords = ";".join(
        f"{lon:.6f},{lat:.6f}" for lon, lat in (gcj02_to_wgs84(s.lon, s.lat) for s in stops))
    url = OSRM_URL + coords + "?overview=false&steps=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dsh-travel-guide/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] OSRM 不可用（{exc}），回落到直线距离", file=sys.stderr)
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        print(f"[warn] OSRM 返回 {data.get('code')}，回落到直线距离", file=sys.stderr)
        return None
    route = data["routes"][0]
    legs = []
    for leg in route.get("legs", []):
        dist = float(leg["distance"])
        if mode == "car":
            dur = float(leg["duration"])
        else:
            dur = dist / 1000.0 / SPEED_KMH[mode] * 3600.0
        legs.append({"distance_m": dist, "duration_s": dur})
    return {
        "legs": legs,
        "total_m": sum(l["distance_m"] for l in legs),
        "total_s": sum(l["duration_s"] for l in legs),
        "source": "OSRM / OpenStreetMap",
        "time_is_estimate": mode != "car",
    }


# --------------------------------------------------------------------------
# 3. 数据模型
# --------------------------------------------------------------------------

@dataclass
class Stop:
    name: str
    lon: float
    lat: float
    note: str = ""

    def pos(self) -> str:
        return f"{self.lon:.6f},{self.lat:.6f}"


DEFAULT_STOPS: List[Stop] = [
    Stop("天安门广场", 116.397128, 39.916527, "Day1 09:00"),
    Stop("故宫博物院", 116.397026, 39.918058, "Day1 10:30"),
    Stop("景山公园", 116.394244, 39.925515, "Day1 15:00"),
    Stop("南锣鼓巷", 116.403263, 39.937004, "Day1 18:00"),
    Stop("什刹海", 116.384842, 39.941011, "Day2 10:00"),
    Stop("鼓楼", 116.393248, 39.948163, "Day2 12:00"),
]

DEFAULT_TITLE = "北京两日 · 示例路线图"
DEFAULT_SUBTITLE = "示意路径（直线连接，非真实导航轨迹）"


# --------------------------------------------------------------------------
# 4. 链接生成（全部无需 Key）
# --------------------------------------------------------------------------

def uri_marker(stops: Sequence[Stop], callnative: int = 0, src: str = SRC) -> str:
    """在地图上标注点位。

    单点 -> https://uri.amap.com/marker?position=lon,lat&name=xxx
    多点 -> https://uri.amap.com/marker?markers=lon,lat,名称|lon,lat,名称   (N<=10)
    """
    if len(stops) == 1:
        s = stops[0]
        return (f"{URI_BASE}/marker?position={s.lon:.6f},{s.lat:.6f}"
                f"&name={_q(s.name)}&src={src}&callnative={callnative}")
    parts = [f"{s.lon:.6f},{s.lat:.6f},{s.name}" for s in stops[:MAX_MARKERS]]
    return (f"{URI_BASE}/marker?markers={_q('|'.join(parts))}"
            f"&src={src}&callnative={callnative}")


def uri_navigation(origin: Stop, dest: Stop, mode: str = "car", policy: int = 0,
                   via: Optional[Stop] = None, callnative: int = 0, src: str = SRC) -> str:
    """调起高德 H5/APP 做路径规划。mode: car / bus / walk / ride。"""
    if mode not in MODES:
        raise ValueError(f"mode 必须是 {MODES} 之一")
    url = (f"{URI_BASE}/navigation?from={origin.lon:.6f},{origin.lat:.6f},{_q(origin.name)}"
           f"&to={dest.lon:.6f},{dest.lat:.6f},{_q(dest.name)}"
           f"&mode={mode}&policy={policy}&src={src}&callnative={callnative}")
    if via is not None:
        url += f"&via={via.lon:.6f},{via.lat:.6f},{_q(via.name)}"
    return url


def ditu_dir_url(origin: Stop, dest: Stop, plan: str = "car") -> str:
    """PC 网页版路线页（实测可直接拼出，无需 Key）。

    实测 uri.amap.com/navigation 在桌面端会 302 到这个形式：
      https://ditu.amap.com/dir?type=car&from%5Blnglat%5D=lon,lat&from%5Bname%5D=A
                               &to%5Blnglat%5D=lon,lat&to%5Bname%5D=B
    """
    a, b = f"{origin.lon:.6f},{origin.lat:.6f}", f"{dest.lon:.6f},{dest.lat:.6f}"
    return (f"https://ditu.amap.com/dir?type={plan}"
            f"&from%5Blnglat%5D={a}&from%5Bname%5D={_q(origin.name)}"
            f"&to%5Blnglat%5D={b}&to%5Bname%5D={_q(dest.name)}")


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def build_links(stops: Sequence[Stop], mode: str = "car") -> dict:
    """一次性产出攻略里最常用的那几条链接。"""
    legs = []
    for i in range(len(stops) - 1):
        legs.append({
            "from": stops[i].name,
            "to": stops[i + 1].name,
            "distance": fmt_distance(haversine_m(stops[i].lon, stops[i].lat,
                                                 stops[i + 1].lon, stops[i + 1].lat)),
            "nav": uri_navigation(stops[i], stops[i + 1], mode=mode),
            "web_dir": ditu_dir_url(stops[i], stops[i + 1], plan=mode),
        })
    return {
        "markers": uri_marker(stops),
        "marker_single": uri_marker([stops[0]]),
        "legs": legs,
        "total_distance": fmt_distance(sum(
            haversine_m(stops[i].lon, stops[i].lat, stops[i + 1].lon, stops[i + 1].lat)
            for i in range(len(stops) - 1))),
    }


# --------------------------------------------------------------------------
# 5. SVG 绘制
# --------------------------------------------------------------------------

def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _text_w(s: str, size: float) -> float:
    """估算文本宽度：CJK 按 1em，ASCII 按 0.56em。"""
    return sum((1.0 if ord(ch) > 0x2E80 else 0.56) * size for ch in s)


def _project(stops: Sequence[Stop], width: int, height: int, pad: int,
             top_pad: int = 0) -> Tuple[List[Tuple[float, float]], float, float]:
    """等距圆柱投影（按中心纬度收缩经度）。

    返回 (像素坐标列表, 每度对应 x 像素, 每度对应 y 像素)。
    为了不让窄长路线缩成一条细线，允许横纵做有限的不等比拉伸
    （上限 DISTORT_MAX 倍）——示意图专用，比例尺会据此自动隐藏。
    """
    lat0 = sum(s.lat for s in stops) / len(stops)
    kx = math.cos(math.radians(lat0))
    pts_deg = [(s.lon * kx, s.lat) for s in stops]
    xs = [p[0] for p in pts_deg]
    ys = [p[1] for p in pts_deg]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    spanx = max(maxx - minx, 1e-5)
    spany = max(maxy - miny, 1e-5)
    aw, ah = max(width - 2 * pad, 1), max(height - 2 * pad - top_pad, 1)
    sx, sy = aw / spanx, ah / spany
    if sx > sy * DISTORT_MAX:
        sx = sy * DISTORT_MAX
    if sy > sx * DISTORT_MAX:
        sy = sx * DISTORT_MAX
    offx = (aw - spanx * sx) / 2
    offy = (ah - spany * sy) / 2
    out = [(pad + offx + (x - minx) * sx, height - pad - offy - (y - miny) * sy)
           for x, y in pts_deg]
    return out, sx, sy


def _box_hits_rect(b: Tuple[float, float, float, float],
                    r: Tuple[float, float, float, float], m: float = 0.0) -> bool:
    bx, by, bw, bh = b
    rx, ry, rw, rh = r
    return not (bx + bw + m < rx or bx > rx + rw + m or by + bh + m < ry or by > ry + rh + m)


def _box_hits_route(b: Tuple[float, float, float, float],
                    pts: Sequence[Tuple[float, float]], m: float = 4.0) -> bool:
    """标签是否压在路线上（沿每段线采样判定）。"""
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        n = max(6, int(math.hypot(x2 - x1, y2 - y1) / 6))
        for k in range(n + 1):
            t = k / n
            if _box_hits_rect(b, (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, 1, 1), m):
                return True
    return False


def _label_layout(stops: Sequence[Stop], pts: Sequence[Tuple[float, float]],
                  width: int, height: int, top_limit: int = 8) -> List[Tuple[float, float]]:
    """给每个点位安排标签左上角，避让画布边界、其它标签、其它点位和路线。"""
    placed: List[Tuple[float, float, float, float]] = []
    out: List[Tuple[float, float]] = []
    for idx, (s, (x, y)) in enumerate(zip(stops, pts)):
        tw = _text_w(s.name, 15.0)
        bw, bh = tw + 16, 26
        cands = [
            (x + 24, y - bh / 2), (x - 24 - bw, y - bh / 2),
            (x - bw / 2, y - 22 - bh), (x - bw / 2, y + 22),
            (x + 24, y + 18), (x - 24 - bw, y + 18),
            (x + 24, y - 18 - bh), (x - 24 - bw, y - 18 - bh),
        ]
        others = [p for j, p in enumerate(pts) if j != idx]
        chosen: Optional[Tuple[float, float, float, float]] = None
        for strict in (True, False):
            for bx, by in cands:
                if bx < 8 or bx + bw > width - 8 or by < top_limit or by + bh > height - 8:
                    continue
                box = (bx, by, bw, bh)
                if any(_box_hits_rect(box, pr, 2) for pr in placed):
                    continue
                if any(_box_hits_rect(box, (px - 17, py - 17, 34, 34)) for px, py in others):
                    continue
                if strict and _box_hits_route(box, pts):
                    continue
                chosen = box
                break
            if chosen:
                break
        if chosen is None:
            chosen = (min(max(x + 24, 8), width - 8 - bw), y - bh / 2, bw, bh)
        placed.append(chosen)
        out.append((chosen[0], chosen[1]))
    return out


def render_svg(stops: Sequence[Stop], title: str = DEFAULT_TITLE,
               subtitle: str = DEFAULT_SUBTITLE,
               width: int = 1080, height: int = 760, mode: str = "car",
               live: Optional[dict] = None) -> str:
    pad = 76
    top_pad = 78
    pts, sx, sy = _project(stops, width, height, pad, top_pad)
    labels = _label_layout(stops, pts, width, height, pad + top_pad)
    total = sum(haversine_m(stops[i].lon, stops[i].lat, stops[i + 1].lon, stops[i + 1].lat)
                for i in range(len(stops) - 1))
    mode_cn = {"car": "驾车", "bus": "公交", "walk": "步行", "ride": "骑行"}[mode]

    L: List[str] = []
    a = L.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
      f'viewBox="0 0 {width} {height}" font-family="{FONT}">')
    a('<defs>')
    a(f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
      f'<stop offset="0" stop-color="{C_BG_TOP}"/><stop offset="1" stop-color="{C_BG_BOTTOM}"/>'
      f'</linearGradient>')
    a('<filter id="sh" x="-40%" y="-40%" width="180%" height="180%">'
      '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#14315c" flood-opacity="0.20"/>'
      '</filter>')
    a('</defs>')

    # 背景 + 网格
    a(f'<rect width="{width}" height="{height}" fill="url(#bg)"/>')
    step = 54
    for gx in range(0, width + 1, step):
        a(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{height}" stroke="{C_GRID}" stroke-width="1"/>')
    for gy in range(0, height + 1, step):
        a(f'<line x1="0" y1="{gy}" x2="{width}" y2="{gy}" stroke="{C_GRID}" stroke-width="1"/>')

    # 路线：先画宽描边做光晕，再画主线
    d = " ".join(("M" if i == 0 else "L") + f" {x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
    a(f'<path d="{d}" fill="none" stroke="{C_ROUTE_HALO}" stroke-opacity="0.15" '
      f'stroke-width="19" stroke-linecap="round" stroke-linejoin="round"/>')
    a(f'<path d="{d}" fill="none" stroke="{C_ROUTE}" stroke-width="5" '
      f'stroke-linecap="round" stroke-linejoin="round"/>')

    # 方向箭头（每段中点一个）
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        a(f'<path d="M -7 -5 L 6 0 L -7 5 Z" fill="{C_ROUTE}" stroke="#ffffff" '
          f'stroke-width="1.5" transform="translate({mx:.1f},{my:.1f}) rotate({ang:.1f})"/>')

    # 点位
    for i, ((x, y)) in enumerate(pts):
        color = C_START if i == 0 else (C_END if i == len(stops) - 1 else C_POI)
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="#ffffff" opacity="0.95"/>')
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13.5" fill="{color}" filter="url(#sh)"/>')
        a(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="13.5" '
          f'font-weight="700" fill="#ffffff">{i + 1}</text>')

    # 标签
    for (s, (bx, by)) in zip(stops, labels):
        bw, bh = _text_w(s.name, 15.0) + 16, 26
        a(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh}" rx="7" '
          f'fill="#ffffff" opacity="0.9"/>')
        a(f'<text x="{bx + 8:.1f}" y="{by + 18:.1f}" font-size="15" font-weight="600" '
          f'fill="{C_TEXT}">{_esc(s.name)}</text>')

    # 标题
    a(f'<text x="56" y="54" font-size="28" font-weight="700" fill="{C_TEXT}">{_esc(title)}</text>')
    a(f'<text x="56" y="80" font-size="14" fill="{C_MUTED}">{_esc(subtitle)}</text>')

    # 信息卡（右上，避开路线区）
    if live:
        rows = [("点位", f"{len(stops)} 处"),
                ("实际路程", fmt_distance(live["total_m"])),
                ("预计耗时", fmt_duration(live["total_s"], live["time_is_estimate"])),
                ("出行方式", mode_cn)]
    else:
        rows = [("点位", f"{len(stops)} 处"),
                ("直线总里程", fmt_distance(total)),
                ("出行方式", mode_cn)]
    cw, ch = 236, 32 + 27 * len(rows)
    cx, cy = width - 56 - cw, 18
    a(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="12" fill="#ffffff" '
      f'opacity="0.94" stroke="{C_GRID}"/>')
    for k, (kk, vv) in enumerate(rows):
        a(f'<text x="{cx + 18}" y="{cy + 30 + k * 27}" font-size="13.5" fill="{C_MUTED}">{kk}</text>')
        a(f'<text x="{cx + cw - 18}" y="{cy + 30 + k * 27}" font-size="13.5" font-weight="600" '
          f'text-anchor="end" fill="{C_TEXT}">{vv}</text>')

    # 比例尺（仅在等比投影下绘制，避免误导）
    if abs(sx / sy - 1.0) < 0.02:
        mpp = M_PER_DEG / sx
        target = 130.0 * mpp
        nice = min([50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000],
                   key=lambda v: abs(v - target))
        px = nice / mpp
        sbx, sby = 56, height - 66
        a(f'<line x1="{sbx}" y1="{sby}" x2="{sbx + px:.1f}" y2="{sby}" '
          f'stroke="{C_TEXT}" stroke-width="2"/>')
        a(f'<line x1="{sbx}" y1="{sby - 5}" x2="{sbx}" y2="{sby + 5}" '
          f'stroke="{C_TEXT}" stroke-width="2"/>')
        a(f'<line x1="{sbx + px:.1f}" y1="{sby - 5}" x2="{sbx + px:.1f}" y2="{sby + 5}" '
          f'stroke="{C_TEXT}" stroke-width="2"/>')
        a(f'<text x="{sbx}" y="{sby + 21}" font-size="12.5" fill="{C_MUTED}">{nice / 1000:g} km</text>')

    # 页脚
    a(f'<text x="56" y="{height - 26}" font-size="12" fill="{C_MUTED}">'
      f'坐标系 GCJ-02（高德）· 示意路线，非导航轨迹</text>')
    a('</svg>')
    return "\n".join(L)


def render_html(svg: str, links: dict, title: str,
                live: Optional[dict] = None) -> str:
    def _live_cell(i: int) -> str:
        if not live or i >= len(live["legs"]):
            return ""
        leg = live["legs"][i]
        return (f'<br><span class="live">实测 {fmt_distance(leg["distance_m"])} · '
                f'{fmt_duration(leg["duration_s"], live["time_is_estimate"])}</span>')

    rows = "\n".join(
        f'<tr><td>{i + 1}</td><td>{_esc(l["from"])} → {_esc(l["to"])}</td>'
        f'<td>{l["distance"]}{_live_cell(i)}</td>'
        f'<td><a href="{_esc(l["nav"])}" target="_blank" rel="noopener">高德导航</a></td>'
        f'<td><a href="{_esc(l["web_dir"])}" target="_blank" rel="noopener">网页路线</a></td></tr>'
        for i, l in enumerate(links["legs"]))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
 body{{margin:0;background:#eef3fa;font-family:{FONT};color:{C_TEXT}}}
 .wrap{{max-width:1120px;margin:0 auto;padding:24px}}
 .card{{background:#fff;border-radius:16px;padding:16px;box-shadow:0 6px 24px #14315c1a;margin-bottom:20px}}
 svg{{width:100%;height:auto;border-radius:12px;display:block}}
 table{{width:100%;border-collapse:collapse;font-size:14px}}
 th,td{{padding:10px 8px;border-bottom:1px solid #eef2f8;text-align:left}}
 th{{color:{C_MUTED};font-weight:600}}
 a{{color:{C_ROUTE};text-decoration:none}} a:hover{{text-decoration:underline}}
 .live{{color:#2f7d4f;font-size:12.5px}}
 .hint{{font-size:13px;color:{C_MUTED};margin-top:12px;line-height:1.7}}
</style></head>
<body><div class="wrap">
<div class="card">{svg}</div>
<div class="card">
<table><thead><tr><th>#</th><th>路段</th><th>直线距离</th><th>导航</th><th>网页版</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="hint">
链接由高德 URI API 生成，无需 Key。微信内置浏览器能打开 H5 页面，但
<code>callnative=1</code> 在微信 / QQ 内置浏览器里无法唤起高德 App（官方文档明确说明），
要导航请点右上角「在浏览器中打开」。合计 {links['total_distance']}（直线距离，实际路程更长）。
</div></div></div></body></html>"""




# --------------------------------------------------------------------------
# 6. Key 读取与校验（可选能力，仅当你真的要调 Web 服务 API 时才需要）
#    存放顺序：环境变量 AMAP_MAPS_API_KEY
#              > ~/.dsh/amap/credentials.json  ({"amap_key": "...", "security_key": ""})
#              > ~/.dsh/amap/key   (纯文本一行)
#    绝不落在工作区、绝不进 git。
# --------------------------------------------------------------------------

KEY_ENV = "AMAP_MAPS_API_KEY"
KEY_DIR = Path.home() / ".dsh" / "amap"
KEY_JSON = KEY_DIR / "credentials.json"
KEY_TXT = KEY_DIR / "key"


def load_key() -> Tuple[Optional[str], str]:
    """返回 (key, 来源说明)。都没有则 (None, 提示)。"""
    import os
    env = os.environ.get(KEY_ENV, "").strip()
    if env:
        return env, f"环境变量 {KEY_ENV}"
    try:
        if KEY_JSON.is_file():
            data = json.loads(KEY_JSON.read_text(encoding="utf-8"))
            k = str(data.get("amap_key", "")).strip()
            if k:
                return k, str(KEY_JSON)
    except Exception:
        pass
    try:
        if KEY_TXT.is_file():
            k = KEY_TXT.read_text(encoding="utf-8").strip()
            if k:
                return k, str(KEY_TXT)
    except Exception:
        pass
    return None, f"未找到（期望 {KEY_ENV} 或 {KEY_JSON}）"


def check_key(timeout: float = 8.0) -> int:
    """用地理编码接口验证 key 是否可用；不打印 key 本身。"""
    import urllib.parse
    import urllib.request
    key, where = load_key()
    if not key:
        print(f"[x] {where}")
        print(f"    申请：https://console.amap.com/dev/key/app  （服务平台选 Web 服务）")
        print(f"    保存：mkdir -p {KEY_DIR} && chmod 700 {KEY_DIR}")
        print(f"          printf '%s' '你的KEY' > {KEY_TXT} && chmod 600 {KEY_TXT}")
        return 2
    masked = key[:4] + "*" * max(0, len(key) - 8) + key[-4:] if len(key) > 8 else "****"
    q = urllib.parse.urlencode({"key": key, "address": "北京天安门", "city": "北京"})
    url = f"https://restapi.amap.com/v3/geocode/geo?{q}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # 网络/代理问题
        print(f"[x] 请求失败：{e}")
        return 1
    if str(data.get("status")) == "1" and data.get("geocodes"):
        g = data["geocodes"][0]
        print(f"[ok] key 可用（来源 {where}，{masked}）")
        print(f"     北京天安门 -> {g.get('location')}  ({g.get('formatted_address', '')[:40]})")
        return 0
    print(f"[x] key 不可用：{data.get('info')} ({data.get('infocode')})")
    return 1


# --------------------------------------------------------------------------
# 7. CLI
# --------------------------------------------------------------------------

def load_stops(path: Optional[str], from_wgs84: bool) -> Tuple[List[Stop], str, str]:
    title, subtitle = DEFAULT_TITLE, DEFAULT_SUBTITLE
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            raw = data
        else:
            raw = data.get("stops", [])
            title = data.get("title", title)
            subtitle = data.get("subtitle", subtitle)
        stops = [Stop(str(r["name"]), float(r["lon"]), float(r["lat"]), r.get("note", ""))
                 for r in raw]
    else:
        stops = list(DEFAULT_STOPS)
    if from_wgs84:
        for s in stops:
            s.lon, s.lat = wgs84_to_gcj02(s.lon, s.lat)
    if len(stops) < 2:
        raise SystemExit("至少需要 2 个点位")
    return stops, title, subtitle


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="零 Key 高德路线图生成器：SVG 示意图 + URI 分享链接")
    ap.add_argument("--out", default="行程/_demo_route.svg", help="SVG 输出路径")
    ap.add_argument("--html", default=None, help="同时输出带链接的 HTML")
    ap.add_argument("--links", default=None, help="把链接清单写成 JSON")
    ap.add_argument("--from-json", default=None, help="从 JSON 读点位")
    ap.add_argument("--from-wgs84", action="store_true", help="输入是 GPS 原始坐标，先转 GCJ-02")
    ap.add_argument("--mode", default="car", choices=MODES, help="出行方式")
    ap.add_argument("--title", default=None, help="覆盖标题")
    ap.add_argument("--live", action="store_true",
                    help="用 OSRM 公共路由算真实路程/耗时（无需 Key，联网）")
    ap.add_argument("--check-key", action="store_true",
                    help="只检查 AMAP_MAPS_API_KEY / ~/.dsh/amap 里的 key 是否可用")
    args = ap.parse_args(argv)

    if args.check_key:
        return check_key()

    stops, title, subtitle = load_stops(args.from_json, args.from_wgs84)
    if args.title:
        title = args.title

    live = osrm_live(stops, mode=args.mode) if args.live else None
    svg = render_svg(stops, title=title, subtitle=subtitle, mode=args.mode, live=live)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")

    links = build_links(stops, mode=args.mode)

    if args.links:
        p = Path(args.links)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.html:
        hp = Path(args.html)
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(render_html(svg, links, title, live=live), encoding="utf-8")

    print(f"[ok] SVG  -> {out.resolve()}  ({out.stat().st_size} bytes)")
    if args.html:
        print(f"[ok] HTML -> {Path(args.html).resolve()}")
    if args.links:
        print(f"[ok] JSON -> {Path(args.links).resolve()}")
    print(f"[i]  点位 {len(stops)} 个，直线总里程 {links['total_distance']}（{args.mode}）")
    if live:
        print(f"[i]  实际路程 {fmt_distance(live['total_m'])}，"
              f"{'约 ' if live['time_is_estimate'] else ''}"
              f"{fmt_duration(live['total_s'])}（{live['source']}）")
    print(f"[i]  多点标注链接: {links['markers']}")
    for l in links["legs"]:
        print(f"      {l['from']} → {l['to']}  {l['distance']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
