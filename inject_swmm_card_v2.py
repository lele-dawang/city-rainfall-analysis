# -*- coding: utf-8 -*-
"""把"随城市联动"的 SWMM 管网卡片注入 index.html。

与上一版的区别：数据源改为 data/swmm_all_cities.json（16 城压缩结果，约 6 KB），
卡片内插值改为按当前选中城市取值，因此切换城市即切换卡片。

运行：python inject_swmm_card_v2.py
"""
from __future__ import annotations

import io
import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(ROOT, "index.html")

with io.open(os.path.join(ROOT, "data", "swmm_all_cities.json"), encoding="utf-8") as f:
    ALL = json.load(f)

# 只保留前端需要的字段，进一步压缩体积
KEYS = ("bn", "d2", "dur", "scen", "scan", "on")
pack = {c: {k: v[k] for k in KEYS if k in v} for c, v in ALL.items()}
data_js = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
print(f"内联数据: {len(pack)} 城，{len(data_js):,} 字符")

# ---------------------------------------------------------------- JS 块（顶层）
TOP_JS = '''
/* ---------- 各城市排水管网水力校核结果（由 swmm_all_cities.py 生成） ---------- */
const SWMM = __SWMM_DATA__;

/* 短历时设计雨量表 */
function swDurTable(dur){
  const rows = [["1h","1 h"],["2h","2 h"],["3h","3 h"],["6h","6 h"],["24h","24 h"]];
  const PAD = 'style="padding:5px 0;border-top:1px solid #eef4f7"';
  let h = '<div style="overflow-x:auto;margin:6px 0 2px"><table style="width:100%;border-collapse:collapse;font-size:12.5px;text-align:center;min-width:420px">'
    + '<tr style="color:var(--muted);font-size:11.5px">'
    + '<th style="text-align:left;padding:4px 0;font-weight:600">历时</th>'
    + '<th style="padding:4px 0;font-weight:600">2 年</th><th style="padding:4px 0;font-weight:600">5 年</th>'
    + '<th style="padding:4px 0;font-weight:600">10 年</th><th style="padding:4px 0;font-weight:600">20 年</th>'
    + '<th style="padding:4px 0;font-weight:600">实测最大</th></tr>';
  rows.forEach(([k, label]) => {
    const d = dur[k];
    if(!d) return;
    h += `<tr><td style="padding:5px 0;border-top:1px solid #eef4f7;text-align:left;font-weight:600">${label}</td>`
       + `<td ${PAD}>${d[0]}</td><td ${PAD}>${d[1]}</td><td ${PAD}>${d[2]}</td>`
       + `<td ${PAD}><b>${d[3]}</b></td><td ${PAD}><span style="color:#b45309">${d[4]}</span></td></tr>`;
  });
  return h + '</table></div>';
}

/* 生成当前城市的管网卡片（无数据时返回空串） */
function swCard(name){
  const s = SWMM[name];
  if(!s) return '';
  const scen = s.scen, on = s.on;
  const rain20 = s.d2[3];
  const onsetTxt = on
    ? `约 <b style="color:var(--accent)">${on} mm/2 h</b>（约 ${(on/2).toFixed(1)} mm/h 平均雨强），约为 20 年一遇设计值的 ${(on/rain20).toFixed(1)} 倍。该值可作为<b>排水防涝预警的雨强阈值参考</b>。`
    : `在本模型的扫描范围（至 20 年一遇设计值的 5 倍）内<b>未出现检查井溢流</b>，说明该城市降雨条件下这套管网的余量充足。`;
  return `
    <div class="card"><h2>🏗 排水管网水力模型（SWMM）· ${name}</h2>
      <div class="note" style="margin-top:0">
        同一套<b>概化管网</b>（服务面积 5.00 ha、综合径流系数约 0.60、7 座检查井 + 7 段管道 DN300~DN600、井深 2.5 m）
        在 <b>${name}</b> 降雨条件下的校核结果。管网按常规小区布置形式<b>概化</b>（非实测 GIS 拓扑），
        各城市共用同一套管网，<b>变化的只有降雨输入</b>。用途为方案级校核与内涝风险比较。
      </div>
      <div class="chart" id="c5"></div>
      <div class="note">纵轴为<b>最大满流比</b>（管段最大流量 ÷ 满流流量），图中虚线为满流线（比值 = 1.0）。
        满流比 &gt; 1.0 表示管道由无压满流转为<b>承压运行</b>（水力坡度线超过管顶）。
        前四根柱为按 2 h 设计暴雨演算，最后一根为实测最不利降雨过程。</div>

      <div style="font-size:13px;font-weight:700;color:var(--ink);margin:16px 0 4px">
        短历时设计雨量（1~24 h，超阈值抽样 POT 含去丛，阈值 3 mm）</div>
      ${swDurTable(s.dur)}
      <div class="note">单位 mm。基于 ${name} 近 5.75 年<b>逐小时</b>降雨（ERA5 再分析）估算（本地有缓存记录的城市）。
        <b>去丛是必须的</b>——滚动窗口直接取样会把同一场雨的相邻时刻重复计入，使年事件率虚高、设计值偏大。</div>

      <div style="font-size:13px;font-weight:700;color:var(--ink);margin:16px 0 4px">
        内涝临界雨量（防涝预警阈值）</div>
      <div class="chart" id="c6"></div>
      <div class="note">横轴为 2 h 降雨量（mm），左轴为地面积水总量（m³），右轴为溢流检查井数。
        把 20 年一遇设计雨型逐级放大，考察检查井开始溢流（地面积水）的临界点：${onsetTxt}</div>

      <div class="concl" style="margin-top:12px">
        ${name} 按"24 h 雨量平均强度"初选管径（上方 Q=ΨqF，q=P/24），
        在 2 年一遇时最大满流比 <b>${scen[0][2].toFixed(2)}</b>（承压 <b>${scen[0][3]}/7</b> 段）；
        <b>20 年一遇</b>时达 <b>${scen[3][2].toFixed(2)}</b>（承压 <b>${scen[3][3]}/7</b> 段）；
        实测极端降雨过程下达 <b>${scen[4][2].toFixed(2)}</b>（承压 ${scen[4][3]}/7 段）。
        短历时峰值强度可达 24 h 平均强度的数倍——这正是<b>用平均强度估算设计流量会低估峰值流量</b>的直接证据，
        也说明必须引入短历时频率分析与管网水力模型。
      </div>
      <div class="note">局限：① 管网为概化管网，非实测 GIS；② ERA5 逐小时数据无法分辨小时内雨强脉动，
        短历时（&lt;1 h）峰值存在低估；③ 雨型参数由 POT 的 1 h/2 h 比值率定，与当地实测雨型仍有差异；
        ④ 样本 5.75 年，POT 重现期估计置信区间较宽；⑤ 未考虑管网沉积、堵塞与地下水入渗。
        正式设计应采用当地 ≥20 年暴雨资料与当地暴雨强度公式（GB 50014）。</div>
    </div>`;
}
'''.replace("__SWMM_DATA__", data_js)

# ---------------------------------------------------------------- 图表代码
CHART_JS = '''
  /* ---------- SWMM 管网卡片图表（随城市联动） ---------- */
  if(_sw){
    const c5 = mkChart("c5");
    if(c5) c5.setOption({
      grid:{ left:44, right:14, top:30, bottom:34 },
      tooltip:{ trigger:"axis",
        formatter: p => `${p[0].axisValue}<br/>降雨 ${_sw.scen[p[0].dataIndex][1]} mm<br/>最大满流比 <b>${p[0].value}</b><br/>承压管道 ${_sw.scen[p[0].dataIndex][3]}/7 段` },
      xAxis:{ type:"category", axisLabel:{ fontSize:11, color:"#8aa3ad" },
        data: _sw.scen.map(s => s[0]) },
      yAxis:{ type:"value", max:3.4, axisLabel:{ color:"#8aa3ad" } },
      series:[{
        type:"bar", barMaxWidth:46,
        data: _sw.scen.map((s, i) => ({ value:s[2],
          itemStyle:{ color:["#7dd3fc","#0ea5e9","#0284c7","#075985","#7f1d1d"][i] } })),
        label:{ show:true, position:"top", fontSize:12, color:"#0f3d4d", formatter:p => p.value.toFixed(2) },
        markLine:{ silent:true, symbol:"none",
          lineStyle:{ color:"#4a6b78", type:"dashed" }, data:[{ yAxis:1 }] }
      }],
      graphic:[{ type:"text", left:56, top:6,
        style:{ text:"- - - 满流（无压流上限）", fontSize:10, fill:"#4a6b78" } }]
    });
    const c6 = mkChart("c6");
    if(c6) c6.setOption({
      grid:{ left:52, right:52, top:34, bottom:30 },
      tooltip:{ trigger:"axis" },
      legend:{ data:["地面积水总量","溢流检查井数"], textStyle:{ fontSize:11, color:"#8aa3ad" }, top:0, right:0 },
      xAxis:{ type:"category", axisLabel:{ fontSize:11, color:"#8aa3ad" },
        data: _sw.scan.map(s => s[0]) },
      yAxis:[
        { type:"value", name:"m³", nameTextStyle:{ color:"#8aa3ad" }, axisLabel:{ color:"#8aa3ad" } },
        { type:"value", name:"井数", max:8, nameTextStyle:{ color:"#8aa3ad" }, axisLabel:{ color:"#8aa3ad" } }
      ],
      series:[
        { name:"地面积水总量", type:"line", smooth:true,
          data: _sw.scan.map(s => s[1]),
          lineStyle:{ color:"#0ea5e9", width:2.5 }, itemStyle:{ color:"#0ea5e9" },
          markLine:{ silent:true, symbol:"none",
            lineStyle:{ color:"#059669", type:"dashdot" },
            label:{ formatter: _sw.on ? ("内涝临界\\n" + _sw.on + " mm/2h") : "", fontSize:10, color:"#059669" },
            data: _sw.on ? [{ xAxis: _sw.scan.findIndex(s => s[2] > 0) }] : [] } },
        { name:"溢流检查井数", type:"line", yAxisIndex:1, smooth:true,
          data: _sw.scan.map(s => s[2]),
          lineStyle:{ color:"#f59e0b", width:2, type:"dashed" }, itemStyle:{ color:"#f59e0b" } }
      ]
    });
  }
'''

# ---------------------------------------------------------------- 注入
src = io.open(IDX, encoding="utf-8", newline="").read()

# 先移除上一版注入的固定版卡片与图表代码（若存在）
if "排水管网水力模型（SWMM）· ${name}" in src:
    raise SystemExit("!! 已经是联动版，未重复注入。")
if "排水管网水力模型（SWMM）· 北京案例" in src:
    # v1 卡片 HTML：从 '    <div class="card"><h2>🏗 排水管网水力模型（SWMM）· 北京案例</h2>' 到其结束
    a = src.find('    <div class="card"><h2>🏗 排水管网水力模型（SWMM）· 北京案例</h2>')
    b = src.find("    </div>`;", a)
    # 必须连卡片的闭合 </div> 一起删掉，否则会留下一个孤立的 </div>（div 数不配平）
    src = src[:a] + src[b + len("    </div>"):]
    print("已移除 v1 固定版卡片 HTML")
    # 还要删掉 v1 的图表 JS 块（含 const SW 旧数据），否则白占约 11KB，
    # 且它先于新版执行、一旦抛错会中断后面所有渲染。
    a2 = src.find("  /* ---------- SWMM 管网模型模块")
    b2 = src.find("  // 计算器状态 + 导出数据快照")
    if a2 >= 0 and b2 > a2:
        print(f"已移除 v1 图表 JS（{b2 - a2:,} 字符）")
        src = src[:a2] + src[b2:]
    else:
        print("!! 未找到 v1 图表 JS 块，请人工确认")

# 1) 顶层：SWMM 数据 + 卡片构造函数（插在 mkChart 之前）
anchor_top = "function mkChart(id){"
if anchor_top not in src:
    raise SystemExit("!! 找不到 mkChart 锚点")
src = src.replace(anchor_top, TOP_JS + "\n" + anchor_top, 1)

# 2) 在 render() 开头构造 _sw / _swCard
#    注意：主模板在 render() 里，而 load() 与 render() 是两个函数——
#    声明必须放在 render() 内部，放进 load() 会报 "_swCard is not defined"。
anchor_render = "function render(a, d, h){"
if anchor_render not in src:
    raise SystemExit("!! 找不到 render() 定义")
src = src.replace(
    anchor_render,
    anchor_render + "\n"
    "  // 当前城市的管网校核数据与卡片（无则返回空串，不显示卡片）\n"
    "  const _sw = SWMM[CITY.name] || null;\n"
    "  const _swCard = swCard(CITY.name);", 1)

# 主模板结尾插入 ${_swCard}
# 注意：v1 卡片的闭合 </div> 与模板结束的 `; 是同一行，删除后会一并消失，
# 因此不能用 "</div>`;" 作锚点。改为在「模板起始 → 下一条注释」区间里取最后一个反引号。
tpl_start = src.find('$("#app").innerHTML = `')
after_tpl = src.find("  // 恢复计算器参数")
if tpl_start < 0 or after_tpl < 0:
    raise SystemExit("!! 找不到模板区间")
tpl_end = src.rfind("`;", tpl_start, after_tpl)
if tpl_end < 0:
    raise SystemExit("!! 找不到模板结尾反引号")
src = src[:tpl_end] + "    ${_swCard}\n" + src[tpl_end:]

# 3) 图表代码插在计算器逻辑之前
anchor_js = "  // 计算器状态 + 导出数据快照"
if anchor_js not in src:
    raise SystemExit("!! 找不到 JS 锚点")
src = src.replace(anchor_js, CHART_JS + "\n" + anchor_js, 1)

# 4) 顶部说明补一句
src = src.replace("推理公式 Q=ΨqF · 个人项目",
                  "推理公式 Q=ΨqF · SWMM 管网水力模型 · 个人项目", 1)
src = src.replace("推理公式 Q=ΨqF · SWMM 管网水力模型 · SWMM 管网水力模型 · 个人项目",
                  "推理公式 Q=ΨqF · SWMM 管网水力模型 · 个人项目", 1)

shutil.copy(IDX, IDX + ".pre_swmm_v2")
io.open(IDX, "w", encoding="utf-8", newline="").write(src)
print(f"[OK] 联动版已注入（备份 index.html.pre_swmm_v2）")
print(f"     index.html {len(src):,} 字符")
