# -*- coding: utf-8 -*-
"""城市排水管网水力模型（SWMM）——概化小区管网 + 设计暴雨内涝风险评估 + 管径校核。

模型定位（诚实口径）：
  · 管网为**概化管网**（按常规住宅小区布置形式概化，非实测 GIS 拓扑）；
  · 降雨为**实测与设计暴雨**，设计值由本项目短历时 POT（去丛）分析给出；
  · 用途是**方案级校核与内涝风险比较**，不是施工图设计。

运行：uv run --with pyswmm python swmm_network_model.py
输出：out/swmm_output/<情景>.inp 与 swmm_results.json、out/SWMM_模拟结果.md
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
SWMMDIR = os.path.join(OUT, "swmm_output")
os.makedirs(SWMMDIR, exist_ok=True)

CITY = "北京"
N_IMP = 0.012       # 不透水区曼宁 n
N_PERV = 0.15       # 透水区曼宁 n
S_IMP = 0.001       # 不透水区洼蓄 mm→m
S_PERV = 0.002

# ---------------------------------------------------------------- 概化管网
# 服务面积合计 5.00 ha；综合径流系数约 0.6（不透水率 60%）
# 坡度按管径分档：DN300→0.003、DN400→0.0015、DN500→0.0012、DN600→0.001
SUBCATCH = [
    #  名称  面积ha 出口井  宽度m  坡度%
    ("S1", 0.60, "J1"),
    ("S2", 0.75, "J2"),
    ("S3", 0.85, "J3"),
    ("S4", 0.95, "J4"),
    ("S5", 0.75, "J5"),
    ("S6", 0.65, "J6"),
    ("S7", 0.45, "J7"),
]
CONDUITS = [
    #  名称  上游 下游  长度m 管径mm 坡度
    ("C1", "J1", "J2", 80, 300, 0.0030),
    ("C6", "J6", "J3", 70, 300, 0.0030),
    ("C2", "J2", "J3", 90, 400, 0.0015),
    ("C3", "J3", "J4", 100, 400, 0.0015),
    ("C7", "J7", "J5", 60, 300, 0.0030),
    ("C4", "J4", "J5", 110, 500, 0.0012),
    ("C5", "J5", "O1", 120, 600, 0.0010),
]
GROUND = None       # 由井底高程 + 井深决定（见 MANHOLE_DEPTH）
MANHOLE_DEPTH = 2.5  # 检查井深 m（管底到路面），符合小区雨水管覆土 1.5~3 m 常规
OUTFALL_INV = 95.00


def build_inverts(city_pipes=None):
    """由排出口向上游推算各检查井井底高程。"""
    pipes = city_pipes or CONDUITS
    inv = {"O1": OUTFALL_INV}
    # 从下游往上游：J5→O1, J4→J5, J3→J4, J2→J3, J1→J2, J6→J3, J7→J5
    order = ["C5", "C4", "C3", "C2", "C1", "C6", "C7"]
    byname = {c[0]: c for c in pipes}
    for name in order:
        n, up, dn, L, D, s = byname[name]
        inv[up] = inv[dn] + L * s
    return inv


def design_storm(city, T, dur_min=120, step_min=5):
    """读取**已率定**的设计雨型（5 min 步长，mm）。

    雨型的 (b, n) 由 POT 的「1 h 雨量 / 2 h 雨量」比值反求得到，
    保证 1 h 与 2 h 两个控制历时都与 POT 设计值一致（见 calibrate_design_storm.py）。
    直接用经验参数（b=10, n=0.7）会让峰值强度远超 1 h 设计雨量，导致
    管网模拟结果偏严重——这是必须避免的内部不一致。
    """
    with io.open(os.path.join(ROOT, "data", "hourly", "率定雨型参数.json"),
                 encoding="utf-8") as f:
        d = json.load(f)
    hy = list(d[city][str(T)]["hyetograph_mm5min"])
    return hy, sum(hy)


def observed_storm(city, top=1):
    """取实测最不利短历时降雨过程（逐小时），线性插值到 5 min 步长。"""
    with io.open(os.path.join(ROOT, "data", "hourly", f"{city}_hourly.json"),
                 encoding="utf-8") as f:
        d = json.load(f)
    t = d["hourly"]["time"]
    p = [x or 0.0 for x in d["hourly"]["precipitation"]]
    best, bi = -1, 0
    for i in range(len(p) - 3):
        v = sum(p[i:i + 3])
        if v > best:
            best, bi = v, i
    a, b_ = max(0, bi - 1), min(len(p), bi + 4)
    hourly = p[a:b_]
    steps = (len(hourly) - 1) * 12 + 1
    out = []
    for k in range(steps):
        pos = k / 12.0
        i0 = int(pos)
        frac = pos - i0
        v = hourly[i0] * (1 - frac) + (hourly[min(i0 + 1, len(hourly) - 1)]) * frac
        out.append(v / 12.0)                 # mm per 5 min
    return out, t[a], sum(hourly)


def write_inp(path, rain_mm5, pipes=None, asc=None):
    pipes = pipes or CONDUITS
    asc = asc or SUBCATCH
    inv = build_inverts(pipes)
    seg = sum(a for _, a, _ in asc)

    L = []
    A = L.append
    A("[TITLE]")
    A(f"概化住宅小区排水管网　服务面积 {seg:.2f} ha　城市: {CITY}")
    A("")
    A("[OPTIONS]")
    A("FLOW_UNITS           CMS")
    A("INFILTRATION         HORTON")
    A("FLOW_ROUTING         DYNWAVE")
    A("LINK_OFFSETS         DEPTH")
    A("MIN_SLOPE            0")
    A("ALLOW_PONDING        NO")
    A("SKIP_STEADY_STATE    NO")
    A("START_DATE           01/01/2020")
    A("START_TIME           00:00:00")
    A(f"REPORT_START_DATE    01/01/2020")
    A(f"REPORT_START_TIME    00:00:00")
    # 降雨结束后仍需退水演算时间，否则模拟在雨停瞬间就结束、看不到积水退去过程
    dur = len(rain_mm5) * 5 + 240        # 降雨历时 + 4 h 退水
    A(f"END_DATE             01/01/2020")
    A(f"END_TIME             {dur//60:02d}:{(dur%60):02d}:00")
    A("SWEEP_START          01/01")
    A("SWEEP_END            12/31")
    A("DRY_DAYS             0")
    A("REPORT_STEP          00:05:00")
    A("WET_STEP             00:05:00")
    A("DRY_STEP             00:05:00")
    A("ROUTING_STEP         0:00:30")
    A("VARIABLE_STEP        0.75")
    A("LENGTHENING_STEP     0")
    A("MIN_SURFAREA         12.557")
    A("NORMAL_FLOW_LIMITED  BOTH")
    A("SYS_FLOW_TOL         5")
    A("LAT_FLOW_TOL         5")
    A("INERTIAL_DAMPING     PARTIAL")
    A("")
    A("[EVAPORATION]")
    A("CONSTANT     0.0")
    A("DRY_ONLY     NO")
    A("")
    A("[RAINGAGES]")
    A(";;Name  Format     Interval  SCF  Source")
    A("RG1     INTENSITY  0:05      1.0  TIMESERIES TS1")
    A("")
    A("[TIMESERIES]")
    A(";;Name  Date        Time     Value")
    for k, v in enumerate(rain_mm5):
        A(f"TS1     01/01/2020  {k*5//60:02d}:{k*5%60:02d}    {v*12:.4f}")
    A("")
    A("[SUBCATCHMENTS]")
    A(";;Name  RainGage  Outlet  Area  %Imperv  Width  %Slope  CurbLen")
    for nm, ar, out in asc:
        A(f"{nm:<8}{'RG1':<11}{out:<9}{ar:<7.2f}{60:<9}{ar*10000/100:<9.1f}{0.5:<9}{0}")
    A("")
    A("[SUBAREAS]")
    A(";;Subcatch  N-Imperv  N-Perv  S-Imperv  S-Perv  %Zero  RouteTo")
    for nm, _, _ in asc:
        A(f"{nm:<11}{N_IMP:<10}{N_PERV:<9}{S_IMP:<10}{S_PERV:<8}{25:<7}OUTLET")
    A("")
    A("[INFILTRATION]")
    A(";;Subcatch  MaxRate  MinRate  Decay  DryTime  MaxInfil")
    for nm, _, _ in asc:
        A(f"{nm:<11}{76.2:<10}{3.81:<9}{4:<8}{7:<9}{0}")
    A("")
    A("[JUNCTIONS]")
    A(";;Name  Elevation  MaxDepth  InitDepth  SurDepth  Aponded")
    for nm in ("J1", "J2", "J3", "J4", "J5", "J6", "J7"):
        e = inv[nm]
        # 井深取常规值 2.5 m：地面高程 = 管底 + 2.5，随管道自然下降
        A(f"{nm:<7}{e:<11.3f}{MANHOLE_DEPTH:<10.3f}{0:<11}{0:<10}{0}")
    A("")
    A("[OUTFALLS]")
    A(";;Name  Elevation  Type  StageData  Gated")
    A(f"{'O1':<7}{OUTFALL_INV:<11.3f}FREE{'':<11}NO")
    A("")
    A("[CONDUITS]")
    A(";;Name  FromNode  ToNode  Length  Roughness  InOffset  OutOffset  InitFlow  MaxFlow")
    for nm, up, dn, ln, D, s in pipes:
        A(f"{nm:<7}{up:<11}{dn:<8}{ln:<8}{0.013:<11}{0:<10}{0:<11}{0:<10}{0}")
    A("")
    A("[XSECTIONS]")
    A(";;Link  Shape     Geom1  Geom2  Geom3  Geom4  Barrels")
    for nm, up, dn, ln, D, s in pipes:
        A(f"{nm:<7}CIRCULAR  {D/1000.0:<8.3f}{0:<8}{0:<8}{0:<8}1")
    A("")
    A("[COORDINATES]")
    A(";;Node  X-Coord  Y-Coord")
    xy = {"J1": (0, 60), "J2": (100, 60), "J3": (190, 60), "J4": (290, 60),
          "J5": (400, 60), "O1": (520, 60), "J6": (190, 0), "J7": (400, 0)}
    for nm, (x, y) in xy.items():
        A(f"{nm:<7}{x:<9}{y}")
    A("")
    A("[REPORT]")
    A("INPUT      NO")
    A("CONTROLS   NO")
    A("SUBCATCHMENTS ALL")
    A("NODES ALL")
    A("LINKS ALL")
    A("")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def run_scenario(path):
    """运行 SWMM，返回节点与管段的关键指标。"""
    from pyswmm import Simulation, Nodes, Links
    node_max, node_flood = {}, {}
    link_maxq, link_maxd = {}, {}
    with Simulation(path) as sim:
        for _ in sim:
            pass
    # 用报告文件更省事：读 .rpt
    rpt = path[:-4] + ".rpt"
    return parse_rpt(rpt)


def _add_row(out, kind, p):
    try:
        if kind == "node" and len(p) >= 7 and p[0].startswith("J"):
            d = out["nodes"].setdefault(p[0], {})
            d["avg_depth_m"] = float(p[2])
            d["max_depth_m"] = float(p[3])
            d["max_hgl"] = float(p[4])
        elif kind == "flood" and len(p) >= 6 and p[0].startswith("J"):
            d = out["nodes"].setdefault(p[0], {})
            d["hours_flooded"] = float(p[1])
            d["flood_vol_m3"] = float(p[-2]) * 1e6 / 1000.0   # 10^6 L → m³
            d["ponded_depth_m"] = float(p[-1])
        elif kind == "link" and len(p) >= 7 and p[0].startswith("C"):
            out["links"][p[0]] = {
                "max_flow_cms": float(p[2]),
                "max_vel_ms": float(p[-3]),
                "max_full_flow_ratio": float(p[-2]),
                "max_full_depth_ratio": float(p[-1]),
            }
    except (ValueError, IndexError):
        pass


def parse_rpt(rpt):
    """从 SWMM 报告里取节点最大深度/积水与管段最大流量/满流比。

    踩过的坑：报告里 "Link Flow Summary" 之后紧跟 "Flow Classification Summary"
    （列是各流态时间占比，如 0.01）。若只在遇到"下一个 Summary 标题"时才切换模式，
    后一张表的行会**覆盖**前一张表已解析出的正确值（表现为满流比全变成 0.01）。
    正确做法：按**虚线边界**精确取出表格体——进入目标小节后跳过前两条虚线，
    读到下一条虚线为止。

    列序（注意 "Time of Max Occurrence" 占 days 与 hr:min 两个 token）：
      Link 行：Link Type |Flow| days hr:min |Veloc| Max/Full_Flow Max/Full_Depth
      → 从右往左取最稳：p[-2]=满流比、p[-1]=满深比、p[-3]=流速
    """
    txt = io.open(rpt, encoding="utf-8", errors="ignore").read()
    lines = txt.split("\n")
    out = {"nodes": {}, "links": {}}
    kinds = {"Node Depth Summary": "node", "Node Flooding Summary": "flood",
             "Link Flow Summary": "link"}
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s in kinds:
            kind = kinds[s]
            dashes, j = 0, i + 1
            while j < len(lines) and dashes < 2:          # 跳到表体起点
                if lines[j].strip().startswith("---"):
                    dashes += 1
                j += 1
            while j < len(lines) and not lines[j].strip().startswith("---"):
                p = lines[j].split()
                if p:
                    _add_row(out, kind, p)
                j += 1
            i = j
        i += 1
    return out


def main():
    # 注意：SWMM 的 C 引擎无法打开含非 ASCII 字符的文件路径（ERROR 303），
    # 因此 .inp 文件名必须用 ASCII，中文情景名只用于报告。
    scenarios = []
    for T in (2, 5, 10, 20):
        rain, depth = design_storm(CITY, T)
        scenarios.append((f"design_T{T}", f"设计暴雨 {T} 年一遇", rain,
                          f"{depth} mm/2h（POT 设计值）"))
    rain_obs, t0, tot = observed_storm(CITY)
    scenarios.append(("observed", "实测最不利过程", rain_obs,
                      f"{t0} 起，3h 合计 {tot:.1f} mm"))

    results = {}
    for key, label, rain, note in scenarios:
        p = os.path.join(SWMMDIR, f"{key}.inp")
        write_inp(p, rain)
        r = run_scenario(p)
        r["label"] = label
        r["note"] = note
        r["rain_total_mm"] = round(sum(rain), 2)
        results[key] = r
        fl = {k: v.get("flood_vol_m3", 0) for k, v in r["nodes"].items()}
        nfl = sum(1 for v in fl.values() if v > 0)
        tot_fl = sum(fl.values())
        mx_full = max((v["max_full_flow_ratio"] for v in r["links"].values()), default=0)
        mx_depth = max((v["max_full_depth_ratio"] for v in r["links"].values()), default=0)
        n_over = sum(1 for v in r["links"].values() if v["max_full_flow_ratio"] > 1.0)
        print(f"{label:<18} 雨量 {sum(rain):>6.1f} mm | 溢流井 {nfl} 个, "
              f"积水 {tot_fl:>7.1f} m³ | 承压管 {n_over}/{len(r['links'])} 条, "
              f"最大满流比 {mx_full:.2f}, 满深比 {mx_depth:.2f}")

    # ---- 内涝临界雨量扫描：放大 20 年一遇设计雨型，找出管网开始地面积水的临界点。
    # 该临界值可直接作为防汛预警的雨强阈值参考。
    print()
    base20, _ = design_storm(CITY, 20)
    scan = []
    for mult in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        rain = [v * mult for v in base20]
        p = os.path.join(SWMMDIR, "scan.inp")
        write_inp(p, rain)
        r = run_scenario(p)
        tot_fl = sum(v.get("flood_vol_m3", 0) for v in r["nodes"].values())
        nfl = sum(1 for v in r["nodes"].values() if v.get("flood_vol_m3", 0) > 0)
        mx = max((v["max_full_flow_ratio"] for v in r["links"].values()), default=0)
        scan.append({"mult": mult, "rain_mm": round(sum(rain), 1), "flood_nodes": nfl,
                     "flood_m3": round(tot_fl, 1), "max_full_ratio": round(mx, 2)})
        print(f"  放大 ×{mult:<4} 雨量 {sum(rain):>6.1f} mm/2h | 溢流井 {nfl} 个, "
              f"积水 {tot_fl:>6.1f} m³ | 最大满流比 {mx:.2f}")
    results["_scan"] = scan
    onset = next((s for s in scan if s["flood_nodes"] > 0), None)
    if onset:
        print(f"\n  → 内涝临界：约 {onset['rain_mm']} mm/2h（约 "
              f"{onset['rain_mm']/2:.1f} mm/h 平均雨强）时开始出现检查井溢流")
    else:
        print("\n  → 扫描范围内未出现地面积水（管网余量充足）")

    with io.open(os.path.join(OUT, "swmm_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("\n[OK] out/swmm_results.json")


if __name__ == "__main__":
    main()
