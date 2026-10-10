# -*- coding: utf-8 -*-
"""短历时暴雨频率分析（带去丛）＋ 设计暴雨雨型生成（供 SWMM 管网模型输入）。

关键方法学修正：滚动窗口逐小时取样会让同一场雨的相邻时刻重复计入，
使 λ（次/年）虚高几十倍、设计值偏大。必须先**去丛**（declustering）：
把时间上连成一片的超阈值段合并成一个事件、只留峰值，并保证事件间
至少间隔 MIT 小时。

运行：python hourly_storm_analysis.py
输出：data/hourly/短历时设计雨量.json、out/典型暴雨过程_*.csv、out/设计雨型_*.csv
"""
from __future__ import annotations

import io
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

U_MM = 3.0            # 超阈值
MIT_H = 24            # 最小事件间隔（小时）
RETURNS = [2, 5, 10, 20]


def load(city):
    with io.open(os.path.join(ROOT, "data", "hourly", f"{city}_hourly.json"),
                 encoding="utf-8") as f:
        d = json.load(f)
    return d["hourly"]["time"], [x or 0.0 for x in d["hourly"]["precipitation"]]


def rolling(p, h):
    n = len(p)
    s = [0.0] * (n + 1)
    for i in range(n):
        s[i + 1] = s[i] + p[i]
    return [s[i + h] - s[i] for i in range(n - h + 1)]


def decluster(r, u=U_MM, mit=MIT_H):
    """把连成一片的超阈值段并成一个事件，取段内峰值；事件间至少隔 mit 步。"""
    peaks, i, n = [], 0, len(r)
    while i < n:
        if r[i] > u:
            j = i
            while j < n and r[j] > u:
                j += 1
            seg = r[i:j]
            k = max(range(len(seg)), key=lambda x: seg[x])
            peaks.append((i + k, seg[k]))
            i = i + k + mit          # 跳过 MIT，保证事件独立
        else:
            i += 1
    return peaks


def pot_fit(peaks, years):
    ex = [v - U_MM for _, v in peaks if v > U_MM]
    if len(ex) < 5:
        return None
    beta = sum(ex) / len(ex)
    lam = len(ex) / years
    return {
        "threshold_mm": U_MM, "events": len(ex), "beta": round(beta, 3),
        "lambda_per_year": round(lam, 3),
        "x_T": {str(T): round(U_MM + beta * math.log(T * lam), 1) for T in RETURNS},
        "max_obs": round(max(r for _, r in peaks), 1),
    }


def chicago_shape(duration_min, r_peak=0.4, step_min=5, b=10.0, n=0.7):
    """归一化的芝加哥雨型形状（只有形状，不含绝对量级）。

    峰前瞬时强度 i_a = [(1-n)·t_a/r + b] / (t_a/r + b)^(n+1)
    峰后瞬时强度 i_b = [(1-n)·t_b/(1-r) + b] / (t_b/(1-r) + b)^(n+1)
    t_a、t_b 为距峰时间（min）；b、n 取国内常用城市值（本处 b=10, n=0.7，
    属**假定值**，须在报告中注明；正式设计应按当地暴雨强度公式取值）。
    返回 (每步雨量的形状数组, 峰位步号)。
    """
    steps = duration_min // step_min
    tp = int(round(r_peak * steps))
    out = []
    for k in range(steps):
        if k < tp:                                   # 峰前
            ta = (tp - k) * step_min
            v = ((1 - n) * ta / r_peak + b) / ((ta / r_peak + b) ** (n + 1))
        else:                                        # 峰后
            tb = (k - tp) * step_min + step_min
            v = ((1 - n) * tb / (1 - r_peak) + b) / ((tb / (1 - r_peak) + b) ** (n + 1))
        out.append(v)
    return out, tp


def chicago_hyetograph(depth_mm, duration_min, r_peak=0.4, step_min=5):
    """把目标雨量按芝加哥雨型分配到各时段，返回每时段雨量（mm）。"""
    shape, _ = chicago_shape(duration_min, r_peak, step_min)
    s = sum(shape)
    return [depth_mm * v / s for v in shape]


def main():
    summary = {}
    for city in ("张家口", "北京"):
        t, p = load(city)
        years = len(p) / 8760.0
        print("=" * 84)
        print(f"{city}　{len(p)} 小时（{years:.2f} 年）　{t[0][:10]} ~ {t[-1][:10]}")
        print("=" * 84)
        res = {}
        for h in (1, 2, 3, 6, 24):
            r = rolling(p, h)
            pk = decluster(r)
            fit = pot_fit(pk, years)
            if fit is None:
                print(f"  {h:>2} h: 去丛后样本不足")
                continue
            res[f"{h}h"] = fit
            print(f"  {h:>2} h　去丛后 {fit['events']:>3} 场, λ={fit['lambda_per_year']:>5.2f}/年, "
                  f"β={fit['beta']:>5.2f} | "
                  + "  ".join(f"{T}年 {fit['x_T'][str(T)]:>6.1f}" for T in RETURNS)
                  + f" mm | 实测最大 {fit['max_obs']:>5.1f} mm")

        # ---- 最不利实测过程（按 1h 强度排，小片区管网的真控制工况）
        r1 = rolling(p, 1)
        pk1 = sorted(decluster(r1), key=lambda x: -x[1])[:3]
        print(f"\n  史上最强的 3 场短历时降雨（按 1h 雨量）:")
        for idx, v in pk1:
            aa, bb = max(0, idx - 2), min(len(p), idx + 25)
            seg = p[aa:bb]
            h2 = max(rolling(seg, 2)) if len(seg) > 2 else 0
            h3 = max(rolling(seg, 3)) if len(seg) > 3 else 0
            print(f"    {t[idx][:13]}  1h={v:.1f}  2h={h2:.1f}  3h={h3:.1f} mm")
        idx1 = pk1[0][0]
        aa, bb = max(0, idx1 - 3), min(len(p), idx1 + 10)
        rows = [(t[i], p[i]) for i in range(aa, bb)]
        with io.open(os.path.join(OUT, f"典型暴雨过程_{city}.csv"), "w",
                     encoding="utf-8") as f:
            f.write("时间,小时雨量_mm\n")
            for ts, v in rows:
                f.write(f"{ts},{v:.1f}\n")
        print(f"    最不利过程的逐时线已存 out/典型暴雨过程_{city}.csv")

        # ---- 设计雨型（2 h 历时，芝加哥型）用于管网模拟
        res["_design_hyetograph"] = {}
        for T in RETURNS:
            d2 = res["2h"]["x_T"][str(T)]
            hy = chicago_hyetograph(d2, 120, r_peak=0.4, step_min=5)
            res["_design_hyetograph"][str(T)] = [round(x, 2) for x in hy]
            fname = os.path.join(OUT, f"设计雨型_{city}_T{T}.csv")
            with io.open(fname, "w", encoding="utf-8") as f:
                f.write("时段_min,雨量_mm\n")
                for k, v in enumerate(hy):
                    f.write(f"{(k+1)*5},{v:.2f}\n")
        print(f"  设计雨型（2 h，芝加哥型 r=0.4）已生成：2/5/10/20 年，"
              f"对应 2h 雨量 {[res['2h']['x_T'][str(T)] for T in RETURNS]} mm")
        print()
        summary[city] = res

    with io.open(os.path.join(ROOT, "data", "hourly", "短历时设计雨量.json"),
                 "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("[OK] data/hourly/短历时设计雨量.json")


if __name__ == "__main__":
    main()
