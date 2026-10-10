# -*- coding: utf-8 -*-
"""把 SWMM 管网模型模块注入 index.html（新增一张卡片，不改动现有任何功能）。

设计原则：
  · 只**新增**：卡片插在"分析结论"之后，图表代码插在计算器逻辑之前；
  · 数据从 swmm_results.json / 短历时设计雨量.json 读取后**内联**进页面，
    不新增网络请求（离线可看，也不受接口波动影响）；
  · 该模块是固定的**北京概化小区案例**，不随城市下拉框变化，页面上须写明。

运行：python inject_swmm_card.py
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(ROOT, "index.html")
CITY = "北京"

with io.open(os.path.join(ROOT, "out", "swmm_results.json"), encoding="utf-8") as f:
    R = json.load(f)
with io.open(os.path.join(ROOT, "data", "hourly", "短历时设计雨量.json"),
             encoding="utf-8") as f:
    SHORT = json.load(f)
with io.open(os.path.join(ROOT, "data", "hourly", "率定雨型参数.json"),
             encoding="utf-8") as f:
    CAL = json.load(f)

KEYS = ["design_T2", "design_T5", "design_T10", "design_T20", "observed"]
scen = []
for k in KEYS:
    r = R[k]
    nfl = sum(1 for v in r["nodes"].values() if v.get("flood_vol_m3", 0) > 0)
    tot = sum(v.get("flood_vol_m3", 0) for v in r["nodes"].values())
    nover = sum(1 for v in r["links"].values() if v["max_full_flow_ratio"] > 1.0)
    mx = max(v["max_full_flow_ratio"] for v in r["links"].values())
    scen.append({"k": k, "label": r["label"], "rain": r["rain_total_mm"],
                 "floodNodes": nfl, "floodM3": round(tot, 1),
                 "over": nover, "total": len(r["links"]), "maxFull": round(mx, 2)})

scan = [{"rain": s["rain_mm"], "floodM3": s["flood_m3"],
         "nodes": s["flood_nodes"], "maxFull": s["max_full_ratio"]} for s in R["_scan"]]
onset = next((s for s in scan if s["nodes"] > 0), None)

drain = {}
for h in ("1h", "2h", "3h", "6h", "24h"):
    d = SHORT[CITY][h]
    drain[h] = {"x": d["x_T"], "obs": d["max_obs"], "n": d["events"]}

payload = {"city": CITY, "drain": drain, "scen": scen, "scan": scan,
           "onset": onset, "area_ha": 5.0, "pipes": 7,
           "hyeto": {str(T): CAL[CITY][str(T)]["hyetograph_mm5min"] for T in (2, 5, 20)}}

# ---------------------------------------------------------------- 表格
PAD = 'style="padding:5px 0;border-top:1px solid #eef4f7"'
rows = []
for h, name in (("1h", "1 h"), ("2h", "2 h"), ("3h", "3 h"),
                ("6h", "6 h"), ("24h", "24 h")):
    d = drain[h]
    rows.append(
        f'<tr><td style="padding:5px 0;border-top:1px solid #eef4f7;'
        f'text-align:left;font-weight:600">{name}</td>'
        f'<td {PAD}>{d["x"]["2"]}</td><td {PAD}>{d["x"]["5"]}</td>'
        f'<td {PAD}>{d["x"]["10"]}</td>'
        f'<td {PAD}><b>{d["x"]["20"]}</b></td>'
        f'<td {PAD}><span style="color:#b45309">{d["obs"]}</span></td></tr>')
table = (
    '<div style="overflow-x:auto;margin:6px 0 2px">'
    '<table style="width:100%;border-collapse:collapse;font-size:12.5px;'
    'text-align:center;min-width:420px">'
    '<tr style="color:var(--muted);font-size:11.5px">'
    '<th style="text-align:left;padding:4px 0;font-weight:600">历时</th>'
    '<th style="padding:4px 0;font-weight:600">2 年</th>'
    '<th style="padding:4px 0;font-weight:600">5 年</th>'
    '<th style="padding:4px 0;font-weight:600">10 年</th>'
    '<th style="padding:4px 0;font-weight:600">20 年</th>'
    '<th style="padding:4px 0;font-weight:600">实测最大</th></tr>'
    + "".join(rows)
    + '</table></div>')

card = f'''
    <div class="card"><h2>🏗 排水管网水力模型（SWMM）· {CITY}案例</h2>
      <div class="note" style="margin-top:0">
        本模块是固定的 <b>概化住宅小区案例</b>（服务面积 5.00 ha，综合径流系数约 0.60，
        7 座检查井 + 7 段管道 DN300~DN600，井深 2.5 m），<b>不随上方城市选择变化</b>。
        管网按常规小区布置形式<b>概化</b>（非实测 GIS 拓扑），用途为方案级校核与内涝风险比较。
      </div>
      <div class="chart" id="c5"></div>
      <div class="note">纵轴为<b>最大满流比</b>（管段最大流量 ÷ 满流流量），图中虚线为满流线（比值 = 1.0）。
        满流比 &gt; 1.0 表示管道由无压满流转为<b>承压运行</b>（水力坡度线超过管顶）。
        工况 1~4 为按短历时（2 h）设计暴雨演算，最后一个为实测最不利降雨过程。</div>

      <div style="font-size:13px;font-weight:700;color:var(--ink);margin:16px 0 4px">
        短历时设计雨量（1~24 h，超阈值抽样 POT 含去丛，阈值 3 mm）</div>
      {table}
      <div class="note">单位 mm。基于近 5.75 年<b>逐小时</b>降雨（ERA5）估算：
        去丛后样本 1 h {drain["1h"]["n"]} 场、2 h {drain["2h"]["n"]} 场、24 h {drain["24h"]["n"]} 场。
        <b>去丛是必须的</b>——滚动窗口直接取样会把同一场雨的相邻时刻重复计入，
        使年事件率虚高、设计值偏大。</div>

      <div style="font-size:13px;font-weight:700;color:var(--ink);margin:16px 0 4px">
        内涝临界雨量（防涝预警阈值）</div>
      <div class="chart" id="c6"></div>
      <div class="note">横轴为 2 h 降雨量（mm），左轴为地面积水总量（m³），右轴为溢流检查井数。
        把 20 年一遇设计雨型逐级放大，考察检查井开始溢流（地面积水）的临界点：
        <b style="color:var(--accent)">约 {onset["rain"] if onset else "—"} mm/2 h</b>
        （约 {onset["rain"]/2 if onset else 0:.1f} mm/h 平均雨强），
        约为 20 年一遇设计值的 {onset["rain"]/drain["2h"]["x"]["20"] if onset else 0:.1f} 倍。
        该值可直接作为<b>排水防涝预警的雨强阈值参考</b>。</div>

      <div class="concl" style="margin-top:12px">
        管网按"24 h 雨量平均强度"初选（本页上方 Q=ΨqF，q=P/24），
        在 2 年一遇时仅 <b>{scen[0]["over"]}/{scen[0]["total"]}</b> 段管道达到满流
        （最大满流比 {scen[0]["maxFull"]:.2f}）、无检查井溢流；
        但 <b>20 年一遇</b>时已有 <b>{scen[3]["over"]}/{scen[3]["total"]}</b> 段转为承压
        （最大满流比 {scen[3]["maxFull"]:.2f}），<b>实测极端过程</b>下达
        <b>{scen[4]["maxFull"]:.2f}</b>。
        短历时峰值强度可达 24 h 平均强度的数倍——这正是<b>用平均强度估算设计流量会低估峰值流量</b>的直接证据，
        也说明必须引入短历时频率分析与管网水力模型。
      </div>
      <div class="note">局限：① 管网为概化管网，非实测 GIS；② ERA5 逐小时数据无法分辨小时内雨强脉动，
        短历时（&lt;1 h）峰值存在低估；③ 雨型参数由 POT 的 1 h/2 h 比值率定，与当地实测雨型仍有差异；
        ④ 样本 5.75 年，POT 重现期估计置信区间较宽（同重现期下逐日口径与逐小时口径的 24 h 设计雨量相差约 12%）；
        ⑤ 未考虑管网沉积、堵塞与地下水入渗。正式设计应采用当地 ≥20 年暴雨资料与当地暴雨强度公式（GB 50014）。</div>
    </div>'''

js = '''
  /* ---------- SWMM 管网模型模块（固定北京案例，不随城市变化） ---------- */
  const SW = __SWMM_DATA__;
  const c5 = mkChart("c5");
  if(c5) c5.setOption({
    grid:{ left:44, right:14, top:22, bottom:34 },
    tooltip:{ trigger:"axis",
      formatter: p => `${p[0].axisValue}<br/>降雨 ${SW.scen[p[0].dataIndex].rain} mm<br/>最大满流比 <b>${p[0].value}</b><br/>承压管道 ${SW.scen[p[0].dataIndex].over}/${SW.scen[p[0].dataIndex].total} 段` },
    xAxis:{ type:"category", axisLabel:{ fontSize:11, color:"#8aa3ad" },
      data: SW.scen.map(s => s.label.replace("设计暴雨 ","").replace("实测最不利过程","实测极端")) },
    yAxis:{ type:"value", max:3.2, axisLabel:{ color:"#8aa3ad" } },
    series:[{
      type:"bar", barMaxWidth:46,
      data: SW.scen.map((s, i) => ({ value:s.maxFull,
        itemStyle:{ color:["#7dd3fc","#0ea5e9","#0284c7","#075985","#7f1d1d"][i] } })),
      label:{ show:true, position:"top", fontSize:12, color:"#0f3d4d", formatter:p => p.value.toFixed(2) },
      markLine:{ silent:true, symbol:"none",
        lineStyle:{ color:"#4a6b78", type:"dashed" },
        data:[{ yAxis:1 }] }
    }],
    // 满流上限的说明放在左上空白处：markLine 的 label 会压在柱子上
    graphic:[{ type:"text", left:56, top:8,
      style:{ text:"- - - 满流（无压流上限）", fontSize:10, fill:"#4a6b78" } }]
  });
  const c6 = mkChart("c6");
  if(c6) c6.setOption({
    grid:{ left:52, right:52, top:34, bottom:30 },
    tooltip:{ trigger:"axis" },
    legend:{ data:["地面积水总量","溢流检查井数"], textStyle:{ fontSize:11, color:"#8aa3ad" }, top:0, right:0 },
    xAxis:{ type:"category", axisLabel:{ fontSize:11, color:"#8aa3ad" },
      data: SW.scan.map(s => s.rain) },
    yAxis:[
      { type:"value", name:"m³", nameTextStyle:{ color:"#8aa3ad" }, axisLabel:{ color:"#8aa3ad" } },
      { type:"value", name:"井数", max:8, nameTextStyle:{ color:"#8aa3ad" }, axisLabel:{ color:"#8aa3ad" } }
    ],
    series:[
      { name:"地面积水总量", type:"line", smooth:true,
        data: SW.scan.map(s => s.floodM3),
        lineStyle:{ color:"#0ea5e9", width:2.5 }, itemStyle:{ color:"#0ea5e9" },
        markLine:{ silent:true, symbol:"none",
          lineStyle:{ color:"#059669", type:"dashdot" },
          label:{ formatter: SW.onset ? ("内涝临界\\n" + SW.onset.rain + " mm/2h") : "", fontSize:10, color:"#059669" },
          data: SW.onset ? [{ xAxis: SW.scan.findIndex(s => s.nodes > 0) }] : [] } },
      { name:"溢流检查井数", type:"line", yAxisIndex:1, smooth:true,
        data: SW.scan.map(s => s.nodes),
        lineStyle:{ color:"#f59e0b", width:2, type:"dashed" }, itemStyle:{ color:"#f59e0b" } }
    ]
  });
'''

data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
js_block = js.replace("__SWMM_DATA__", data_js)

# ---------------------------------------------------------------- 注入
src = io.open(IDX, encoding="utf-8", newline="").read()
if "排水管网水力模型（SWMM）" in src:
    raise SystemExit("!! index.html 里已有 SWMM 模块，未重复注入。")

# 1) 卡片：插在"分析结论"卡片之后
marker = "未来一周降雨总体温和。"
i = src.find(marker)
if i < 0:
    raise SystemExit("!! 找不到卡片锚点")
j = src.find("    </div>`;", i)
if j < 0:
    raise SystemExit("!! 找不到卡片结束锚点")
src = src[:j + len("    </div>")] + card + src[j + len("    </div>"):]

# 2) JS：插在计算器逻辑之前
anchor = "  // 计算器状态 + 导出数据快照"
if anchor not in src:
    raise SystemExit("!! 找不到 JS 锚点")
src = src.replace(anchor, js_block + "\n" + anchor, 1)

# 3) 标题里的方法说明补一句
src = src.replace(
    "推理公式 Q=ΨqF · 个人项目",
    "推理公式 Q=ΨqF · SWMM 管网水力模型 · 个人项目", 1)

shutil.copy(IDX, IDX + ".pre_swmm")
io.open(IDX, "w", encoding="utf-8", newline="").write(src)
print(f"[OK] 已注入 SWMM 模块（备份 index.html.pre_swmm）")
print(f"     内涝临界 {onset['rain'] if onset else '-'} mm/2h，"
      f"情景 {len(scen)} 个，扫描点 {len(scan)} 个")
