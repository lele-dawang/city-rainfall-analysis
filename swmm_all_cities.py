# -*- coding: utf-8 -*-
"""为站点上全部 16 个城市批量跑"短历时频率分析 → 雨型率定 → SWMM 管网校核"。

产出**压缩后的每城关键结果**（约 350 字节/城），供前端内联，实现"选哪个城市就显示哪个城市的管网卡片"。

重要口径（必须如实呈现）：
  · 管网是**同一套概化管网**（5 ha、7 段 DN300~DN600），各城市共用；
    变化的只有降雨输入。因此结论应表述为
    「同一套概化管网在各城市降雨条件下的校核结果」，而非"各城市的实际管网"。

运行：uv run --with pyswmm python swmm_all_cities.py
输出：data/swmm_all_cities.json、out/全城市管网校核汇总.md
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from swmm_network_model import write_inp, run_scenario, SWMMDIR  # noqa: E402
from hourly_storm_analysis import rolling, decluster, pot_fit    # noqa: E402
from calibrate_design_storm import chicago_shape, fit            # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "hourly")
OUT = os.path.join(ROOT, "out")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)
os.makedirs(SWMMDIR, exist_ok=True)

RETURNS = [2, 5, 10, 20]
DURS = (1, 2, 3, 6, 24)
SCAN_MULT = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0)

CITIES = [
    ("张家口", 40.768, 114.886), ("北京", 39.904, 116.407), ("天津", 39.084, 117.201),
    ("上海", 31.230, 121.474), ("广州", 23.129, 113.264), ("成都", 30.573, 104.067),
    ("武汉", 30.593, 114.305), ("西安", 34.342, 108.940), ("深圳", 22.543, 114.058),
    ("杭州", 30.274, 120.155), ("南京", 32.060, 118.797), ("青岛", 36.067, 120.383),
    ("重庆", 29.563, 106.551), ("昆明", 25.039, 102.718), ("哈尔滨", 45.803, 126.535),
    ("兰州", 36.061, 103.834),
]

U_MM = 3.0


def hourly(name, lat, lon):
    """取逐小时降雨（本地缓存优先）。"""
    path = os.path.join(CACHE, f"{name}_hourly.json")
    if os.path.exists(path):
        d = json.load(io.open(path, encoding="utf-8"))
    else:
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "start_date": "2021-01-01", "end_date": "2026-09-30",
            "hourly": "precipitation", "timezone": "Asia/Shanghai"})
        url = "https://archive-api.open-meteo.com/v1/archive?" + q
        for k in range(3):
            try:
                d = json.load(urllib.request.urlopen(url, timeout=180))
                break
            except Exception as e:
                if k == 2:
                    raise
                time.sleep(3)
        json.dump(d, io.open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return d["hourly"]["time"], [x or 0.0 for x in d["hourly"]["precipitation"]]


def hyeto_for(T, b, n, D2):
    s = chicago_shape(b=b, n=n)
    tot = sum(s)
    return [D2 * v / tot for v in s]


def worst_observed(p, t):
    """实测最不利短历时过程（3 h 滑动最大），线性插值到 5 min 步长。"""
    best, bi = -1.0, 0
    for i in range(len(p) - 3):
        v = p[i] + p[i + 1] + p[i + 2]
        if v > best:
            best, bi = v, i
    a, b_ = max(0, bi - 1), min(len(p), bi + 4)
    seg = p[a:b_]
    steps = (len(seg) - 1) * 12 + 1
    out = []
    for k in range(steps):
        pos = k / 12.0
        i0 = int(pos)
        fr = pos - i0
        out.append((seg[i0] * (1 - fr) + seg[min(i0 + 1, len(seg) - 1)] * fr) / 12.0)
    return out, sum(seg), t[a]


def run_city(name, lat, lon, tag):
    t, p = hourly(name, lat, lon)
    years = len(p) / 8760.0
    # ---- 短历时频率分析
    dur = {}
    for h in DURS:
        f = pot_fit(decluster(rolling(p, h)), years)
        dur[f"{h}h"] = f
    # ---- 逐重现期率定雨型参数 (b, n)，控制 1 h / 2 h 比值
    bn, d2, scen = [], [], []
    for T in RETURNS:
        tgt = dur["1h"]["x_T"][str(T)] / dur["2h"]["x_T"][str(T)]
        (b, n, _got), _err = fit(tgt)
        bn.append([b, n])
        D2 = dur["2h"]["x_T"][str(T)]
        d2.append(D2)
        hy = hyeto_for(T, b, n, D2)
        path = os.path.join(SWMMDIR, f"c_{tag}_T{T}.inp")
        write_inp(path, hy)
        r = run_scenario(path)
        mx = max((v["max_full_flow_ratio"] for v in r["links"].values()), default=0)
        nover = sum(1 for v in r["links"].values() if v["max_full_flow_ratio"] > 1.0)
        scen.append([f"{T} 年一遇", round(sum(hy), 1), round(mx, 2), nover])
    # ---- 实测最不利过程
    obs_rain, obs_tot, obs_t0 = worst_observed(p, t)
    path = os.path.join(SWMMDIR, f"c_{tag}_obs.inp")
    write_inp(path, obs_rain)
    r = run_scenario(path)
    obs_mx = max((v["max_full_flow_ratio"] for v in r["links"].values()), default=0)
    obs_over = sum(1 for v in r["links"].values() if v["max_full_flow_ratio"] > 1.0)
    scen.append(["实测极端", round(obs_tot, 1), round(obs_mx, 2), obs_over])
    # ---- 内涝临界扫描（放大 20 年一遇雨型）
    base = hyeto_for(20, bn[3][0], bn[3][1], d2[3])
    scan, onset = [], None
    for m in SCAN_MULT:
        hy = [v * m for v in base]
        path = os.path.join(SWMMDIR, f"c_{tag}_s{int(m*10)}.inp")
        write_inp(path, hy)
        r = run_scenario(path)
        fl = [v.get("flood_vol_m3", 0) for v in r["nodes"].values()]
        tot = round(sum(fl), 1)
        nn = sum(1 for v in fl if v > 0)
        scan.append([round(sum(hy), 1), tot, nn])
        if nn > 0 and onset is None:
            onset = round(sum(hy), 1)
    return {
        "bn": bn,                                   # 各重现期率定参数 [[b,n]×4]
        "d2": [round(x, 1) for x in d2],            # 2 h 设计雨量 T2/T5/T10/T20
        "dur": {f"{h}h": [dur[f"{h}h"]["x_T"][str(T)] for T in RETURNS]
                + [dur[f"{h}h"]["max_obs"]] for h in DURS},
        "scen": scen,                               # [标签, 雨量, 最大满流比, 承压管数]
        "scan": scan,                               # [雨量, 积水m³, 溢流井数]
        "on": onset,                                # 内涝临界雨量 mm/2h
        "obs_t": obs_t0[:10],
    }


def main():
    res, t0 = {}, time.time()
    for i, (nm, la, lo) in enumerate(CITIES, 1):
        s = time.time()
        try:
            res[nm] = run_city(nm, la, lo, f"{i:02d}")
            r = res[nm]
            print(f"[{i:>2}/16] {nm:<4} 2h设计 {r['d2'][-1]:>5} mm | "
                  f"20年满流比 {r['scen'][3][2]:>5} | 实测 {r['scen'][4][2]:>5} | "
                  f"内涝临界 {r['on'] if r['on'] else '未达到'} | {time.time()-s:.0f}s",
                  flush=True)
        except Exception as e:
            print(f"[{i:>2}/16] {nm} 失败: {type(e).__name__} {e}", flush=True)
    json.dump(res, io.open(os.path.join(ROOT, "data", "swmm_all_cities.json"),
                           "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    sz = os.path.getsize(os.path.join(ROOT, "data", "swmm_all_cities.json"))
    print(f"\n[OK] data/swmm_all_cities.json　{sz:,} 字节　"
          f"共 {len(res)} 城　总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
