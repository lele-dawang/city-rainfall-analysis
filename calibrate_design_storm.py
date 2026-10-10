# -*- coding: utf-8 -*-
"""用 POT 短历时设计值率定设计雨型参数（同频率控制）。

为什么要率定：芝加哥雨型的形状由 (r, b, n) 三个参数决定，若直接套用经验值
（如 b=10, n=0.7），得到的 5 min 峰值强度可能远大于 POT 给出的 1 h 设计雨量，
属于**内部不一致**——峰值偏大 → 管网模拟结果（承压、内涝）全部偏严重。

正确做法（同频率控制）：以 POT 得到的「1 h 雨量 / 2 h 雨量」比值为目标，
反求 (b, n)，使雨型的 1 h 滑动最大雨量与 2 h 总雨量之比等于该目标值。
率定后再用 2 h 设计雨量整体缩放，得到可直接用于 SWMM 的雨型。

运行：python calibrate_design_storm.py
输出：data/hourly/率定雨型参数.json、out/设计雨型_率定_*.csv
"""
from __future__ import annotations

import io
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

R_PEAK = 0.4
DUR_MIN = 120
STEP_MIN = 5


def rolling_sum(arr, k):
    return [sum(arr[i:i + k]) for i in range(len(arr) - k + 1)]


def chicago_shape(dur_min=DUR_MIN, step_min=STEP_MIN, r=R_PEAK, b=10.0, n=0.7):
    steps = dur_min // step_min
    tp = int(round(r * steps))
    out = []
    for k in range(steps):
        if k < tp:
            ta = (tp - k) * step_min
            out.append(((1 - n) * ta / r + b) / ((ta / r + b) ** (n + 1)))
        else:
            tb = (k - tp) * step_min + step_min
            out.append(((1 - n) * tb / (1 - r) + b) / ((tb / (1 - r) + b) ** (n + 1)))
    return out


def ratio_1h_2h(b, n):
    s = chicago_shape(b=b, n=n)
    tot = sum(s)
    per_hour = DUR_MIN // 60
    mx1h = max(rolling_sum(s, 60 // STEP_MIN))
    return mx1h / tot, mx1h, tot


def fit(target, b_range=(2.0, 40.0, 0.5), n_range=(0.30, 1.30, 0.01)):
    """网格搜索 (b, n) 使 1h/2h 比值最接近目标。"""
    best, best_err = None, 1e9
    b = b_range[0]
    while b <= b_range[1]:
        n = n_range[0]
        while n <= n_range[1]:
            rt, _, _ = ratio_1h_2h(b, n)
            err = abs(rt - target)
            if err < best_err:
                best_err, best = err, (round(b, 2), round(n, 3), rt)
            n += n_range[2]
        b += b_range[2]
    return best, best_err


def main():
    with io.open(os.path.join(ROOT, "data", "hourly", "短历时设计雨量.json"),
                 encoding="utf-8") as f:
        d = json.load(f)

    out = {}
    for city in ("北京", "张家口"):
        out[city] = {}
        print("=" * 74)
        print(city)
        print("=" * 74)
        for T in (2, 5, 10, 20):
            D1 = d[city]["1h"]["x_T"][str(T)]
            D2 = d[city]["2h"]["x_T"][str(T)]
            target = D1 / D2
            (b, n, got), err = fit(target)
            shape = chicago_shape(b=b, n=n)
            s = sum(shape)
            hy = [D2 * v / s for v in shape]
            # 率定后自检：雨型的 1h 最大雨量应约等于 POT 的 1h 设计值
            chk1 = max(rolling_sum(hy, 12))
            print(f"  {T:>2} 年：POT 1h={D1:>5.1f} 2h={D2:>5.1f} mm（比值 {target:.3f}）"
                  f" → 率定 b={b:<5} n={n:<5}（拟合比值 {got:.3f}）"
                  f" → 雨型 1h={chk1:>5.1f} mm，峰值 5min 强度 "
                  f"{max(hy)*12:>5.1f} mm/h")
            out[city][str(T)] = {"b": b, "n": n, "r": R_PEAK, "D1": D1, "D2": D2,
                                 "hyetograph_mm5min": [round(x, 3) for x in hy],
                                 "check_1h_mm": round(chk1, 2)}
            with io.open(os.path.join(OUT, f"设计雨型_率定_{city}_T{T}.csv"), "w",
                         encoding="utf-8") as f:
                f.write("时段_min,雨量_mm\n")
                for k, v in enumerate(hy):
                    f.write(f"{(k+1)*STEP_MIN},{v:.3f}\n")
        print()

    with io.open(os.path.join(ROOT, "data", "hourly", "率定雨型参数.json"),
                 "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("[OK] data/hourly/率定雨型参数.json")


if __name__ == "__main__":
    main()
