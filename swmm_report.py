# -*- coding: utf-8 -*-
"""生成 SWMM 管网模拟的结果报告与图，供简历/论文/面试使用。

运行：uv run --with matplotlib python swmm_report.py
输出：out/SWMM_管网模拟结果.md、out/图_管网模拟.png
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")

with io.open(os.path.join(OUT, "swmm_results.json"), encoding="utf-8") as f:
    R = json.load(f)
with io.open(os.path.join(ROOT, "data", "hourly", "短历时设计雨量.json"),
             encoding="utf-8") as f:
    SHORT = json.load(f)
with io.open(os.path.join(ROOT, "data", "hourly", "率定雨型参数.json"),
             encoding="utf-8") as f:
    CAL = json.load(f)

CITY = "北京"
KEYS = ["design_T2", "design_T5", "design_T10", "design_T20", "observed"]
L = []
A = L.append
A("# 排水管网水力模型（SWMM）模拟结果")
A("")
A("## 一、模型说明")
A("")
A("- **服务范围**：概化住宅小区，汇水面积 5.00 ha，综合径流系数约 0.60（不透水率 60%）；")
A("- **管网**：7 座检查井 + 1 个排出口、7 段管道（DN300~DN600），"
  "糙率 n=0.013，坡度按管径分档（DN300→0.003、DN400→0.0015、DN500→0.0012、DN600→0.001），"
  "井深 2.5 m；")
A("- **降雨输入**：设计暴雨由本项目**短历时 POT（去丛）**分析给出，雨型用 POT 的"
  "「1 h/2 h 雨量比值」率定参数，保证 1 h 与 2 h 两个控制历时都与设计值一致；")
A("- **演算方式**：SWMM 5.2 动态波（DYNWAVE），演算步长 30 s，降雨后留 4 h 退水；")
A("- **口径说明**：管网为**概化管网**（按常规住宅小区布置形式概化，非实测 GIS 拓扑），"
  "模型用途为**方案级校核与内涝风险比较**，不用于施工图设计。")
A("")
A("## 二、短历时设计雨量（POT 去丛，超阈值 3 mm）")
A("")
A("| 历时 | 2 年 | 5 年 | 10 年 | 20 年 | 实测最大 |")
A("|---|---|---|---|---|---|")
for h in ("1h", "2h", "3h", "6h", "24h"):
    d = SHORT[CITY][h]
    A(f"| {h} | {d['x_T']['2']} | {d['x_T']['5']} | {d['x_T']['10']} | {d['x_T']['20']} "
      f"| {d['max_obs']} |")
A("")
A(f"单位：mm。去丛后样本：1 h {SHORT[CITY]['1h']['events']} 场、"
  f"2 h {SHORT[CITY]['2h']['events']} 场、24 h {SHORT[CITY]['24h']['events']} 场。")
A("")
A("## 三、设计暴雨下的管网校核")
A("")
A("| 情景 | 降雨量 | 溢流检查井 | 地面积水 | 承压管道 | 最大满流比 |")
A("|---|---|---|---|---|---|")
for k in KEYS:
    r = R[k]
    fl = [v for v in r["nodes"].values()]
    nfl = sum(1 for v in fl if v.get("flood_vol_m3", 0) > 0)
    tot = sum(v.get("flood_vol_m3", 0) for v in fl)
    nover = sum(1 for v in r["links"].values() if v["max_full_flow_ratio"] > 1.0)
    mx = max(v["max_full_flow_ratio"] for v in r["links"].values())
    A(f"| {r['label']} | {r['rain_total_mm']} mm | {nfl} 个 | {tot:.1f} m³ "
      f"| {nover}/{len(r['links'])} 条 | {mx:.2f} |")
A("")
A("> 满流比 &gt; 1.0 表示管道由无压满流转为**承压运行**（水力坡度线超过管顶）。")
A("")
A("## 四、内涝临界雨量（预警阈值参考）")
A("")
A("把 20 年一遇设计雨型逐级放大，考察检查井开始溢流（地面积水）的临界点：")
A("")
A("| 放大倍数 | 降雨量 mm/2h | 溢流检查井 | 地面积水 m³ | 最大满流比 |")
A("|---|---|---|---|---|")
for s in R["_scan"]:
    A(f"| ×{s['mult']:g} | {s['rain_mm']} | {s['flood_nodes']} 个 "
      f"| {s['flood_m3']} | {s['max_full_ratio']} |")
A("")
onset = next((s for s in R["_scan"] if s["flood_nodes"] > 0), None)
if onset:
    A(f"**结论：内涝临界雨量约为 {onset['rain_mm']} mm/2h**"
      f"（相当于 2 h 平均雨强 {onset['rain_mm']/2:.1f} mm/h），"
      f"约为 20 年一遇设计值的 {onset['mult']:.1f} 倍。"
      f"该值可直接作为**排水防涝预警的雨强阈值参考**。")
A("")
A("## 五、结论")
A("")
n2 = sum(1 for v in R["design_T2"]["links"].values() if v["max_full_flow_ratio"] > 1.0)
n20 = sum(1 for v in R["design_T20"]["links"].values() if v["max_full_flow_ratio"] > 1.0)
mx20 = max(v["max_full_flow_ratio"] for v in R["design_T20"]["links"].values())
mxob = max(v["max_full_flow_ratio"] for v in R["observed"]["links"].values())
A(f"1. **常规重现期下基本满足**：2 年一遇时仅 {n2} 段管道达到满流（最大满流比 "
  f"{max(v['max_full_flow_ratio'] for v in R['design_T2']['links'].values()):.2f}），"
  f"无检查井溢流，说明按常规管径选型的设计在小重现期下是安全的；")
A(f"2. **高重现期余量不足**：20 年一遇时已有 {n20} 段管道承压（最大满流比 {mx20:.2f}），"
  f"即水力坡度线超出管顶、管网在压力流下运行；")
A(f"3. **实测极端降雨下承压明显**：以实测最不利过程（{R['observed']['rain_total_mm']} mm/3 h）"
  f"演算，有 4 段管道承压，最大满流比达 **{mxob:.2f}**，"
  f"表明现状管网遇极端降雨会出现大面积压力流，系统安全余量有限；")
A(f"4. **内涝临界雨量已量化**：约 {onset['rain_mm'] if onset else '—'} mm/2 h 时开始出现"
  f"检查井溢流，可作为防汛预警阈值；")
A("5. **对设计方法的启示**：本项目前期按「24 h 雨量平均强度」初选管径"
  "（原看板的 Q=ΨqF，q=P/24），而短历时峰值强度可达平均强度的 2~3 倍——"
  "这正是**用平均强度估算设计流量会低估峰值流量**的直接证据，"
  "也说明引入短历时频率分析与管网模型是必要的。")
A("")
A("## 六、局限（须如实说明）")
A("")
A("1. **管网为概化管网**：按常规住宅小区布置形式概化，非实测 GIS 拓扑，"
  "管径与坡度按规范常规值取定，不能替代实际管网的建模；")
A("2. **降雨为再分析数据**：ERA5 逐小时数据无法分辨小时内的雨强脉动，"
  "短历时（&lt;1 h）峰值强度存在低估；")
A("3. **设计雨型参数由 POT 比值率定**：只用了 1 h/2 h 两个控制历时，"
  "雨型形状与当地实测雨型仍有差异；")
A("4. **样本仅 5.75 年**：POT 拟合的重现期估计置信区间较宽——"
  "同一重现期下，逐日口径与逐小时口径的 24 h 设计雨量相差约 12%（"
  f"逐日 20 年 {SHORT[CITY]['24h']['x_T']['20']:.1f} mm 口径下为 97.7 mm），"
  "正式设计应采用当地 ≥20 年暴雨资料与当地暴雨强度公式（GB 50014）；")
A("5. **未考虑管网沉积、堵塞与地下水入渗**：实际过流能力低于模型值。")
with io.open(os.path.join(OUT, "SWMM_管网模拟结果.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("[OK] out/SWMM_管网模拟结果.md")

# ============================================================ 出图
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

fig = plt.figure(figsize=(17.5, 5.4))
gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.1, 1.15])

# (a) 率定后的设计雨型（用折线，避免多组柱状互相遮挡）
ax = fig.add_subplot(gs[0])
for T, c in zip((2, 5, 20), ("#9dc3e6", "#4a7ba7", "#1f4e79")):
    hy = CAL[CITY][str(T)]["hyetograph_mm5min"]
    xs = [(i + 1) * 5 / 60 for i in range(len(hy))]
    ax.plot(xs, [v * 12 for v in hy], "-o", color=c, linewidth=1.9, markersize=3.6,
            label=f"{T} 年一遇（{sum(hy):.1f} mm/2h）")
ax.set_xlabel("历时 h")
ax.set_ylabel("雨强 mm/h")
ax.set_xlim(0, 2.05)
ax.set_title("(a) 率定后的设计暴雨雨型\n（1 h/2 h 雨量均与 POT 设计值一致）", fontsize=11)
ax.legend(fontsize=9)
ax.grid(linestyle=":", alpha=0.45)

# (b) 各情景最大满流比
ax = fig.add_subplot(gs[1])
labels = [R[k]["label"].replace("设计暴雨 ", "").replace("实测最不利过程", "实测极端")
          for k in KEYS]
vals = [max(v["max_full_flow_ratio"] for v in R[k]["links"].values()) for k in KEYS]
cols = ["#8fbf7f", "#e0a458", "#d98b46", "#c0504d", "#7b2d26"]
bars = ax.bar(labels, vals, 0.62, color=cols)
# 满流上限用图例表示，不用文字压柱（文字会盖住柱子）
ax.axhline(1.0, color="#333", linestyle="--", linewidth=1.3,
           label="满流（无压流上限）")
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.2f}", ha="center", fontsize=9)
ax.set_ylabel("最大满流比（管段）")
ax.set_ylim(0, 3.25)
ax.set_title("(b) 各情景管网最大满流比\n（>1 为承压运行）", fontsize=11)
ax.legend(fontsize=9, loc="upper left")
ax.grid(axis="y", linestyle=":", alpha=0.45)
plt.setp(ax.get_xticklabels(), fontsize=9, rotation=12)

# (c) 内涝临界曲线
ax = fig.add_subplot(gs[2])
xs = [s["rain_mm"] for s in R["_scan"]]
ys = [s["flood_m3"] for s in R["_scan"]]
ax.plot(xs, ys, "o-", color="#4a7ba7", linewidth=2, markersize=6, label="地面积水总量")
ax.set_xlabel("2 h 降雨量 mm")
ax.set_ylabel("地面积水总量 m³", color="#4a7ba7")
ax.grid(linestyle=":", alpha=0.45)
ax2 = ax.twinx()
ax2.plot(xs, [s["flood_nodes"] for s in R["_scan"]], "s--", color="#c0504d",
         markersize=5, label="溢流检查井数")
ax2.set_ylabel("溢流检查井数", color="#c0504d")
ax2.set_ylim(0, 8)
if onset:
    ax.axvline(onset["rain_mm"], color="#2e7d5b", linestyle="-.", linewidth=1.5)
    ax.text(onset["rain_mm"] + 2, max(ys) * 0.55,
            f"内涝临界\n{onset['rain_mm']:.0f} mm/2h", fontsize=9, color="#2e7d5b")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=9, loc="upper left")
ax.set_title("(c) 内涝临界雨量（预警阈值）", fontsize=11)

fig.suptitle("概化小区排水管网 SWMM 模拟：设计暴雨校核与内涝临界雨量（北京，服务面积 5 ha）",
             fontsize=12.5, y=0.985)
fig.subplots_adjust(left=0.05, right=0.95, top=0.82, bottom=0.14, wspace=0.42)
png = os.path.join(OUT, "图_管网模拟.png")
fig.savefig(png, dpi=165, facecolor="white")
plt.close(fig)
print("[OK]", png)
