# -*- coding: utf-8 -*-
"""
城市降雨数据采集与排水分析管线 (v2)
=====================================
数据源: Open-Meteo 公开气象 API (https://open-meteo.com)
方法:
  1. 采集近 90 天逐日降雨 + 未来 7 天预报 (past_days=90)
  2. 基础统计: 累计/最大/大雨日/暴雨日/连续无雨
  3. 设计暴雨重现期估算: 超阈值法(POT) + 指数分布 x_T = u + beta*ln(T*lambda)
  4. 雨水设计流量估算: 推理公式 Q = Psi*q*F (q 取 T 年重现期 24h 平均强度)
  5. 归档: data/<城市>_daily.csv + analysis_<城市>.json

用法:
  python fetch_rain.py 张家口 40.768 114.886
  python fetch_rain.py 北京 39.904 116.407
依赖: 仅 Python 标准库 (urllib/json/math/csv)
"""
import sys, json, math, csv, os, datetime
import urllib.request, urllib.parse

API = "https://api.open-meteo.com/v1/forecast"
U = 5.0          # POT 阈值 mm（日降雨 >= 5mm 视为一场独立降雨事件）
PSI = 0.6        # 径流系数（绿地/道路混合，参考 GB50014）
F_HA = 5.0       # 汇水面积 ha（示例小区）
V = 1.0          # 满流圆管初选流速 m/s
DN = [75,100,150,200,250,300,400,500,600,800,1000,1200]

def fetch(url, timeout=20, retries=3):
    """带重试的 GET（国内网络 TLS 偶发重置，重试可显著提高成功率）"""
    import time
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RainfallAnalysis/2.0 (student project)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def return_periods(rain, u=U):
    """超阈值法 + 指数分布: 返回 {T: 24h设计雨量mm}"""
    evs = [r for r in rain if r >= u]
    beta = sum(r - u for r in evs) / len(evs) if evs else 0.0
    ny = max(len(rain) / 365.25, 1e-6)
    lam = len(evs) / ny
    p = lambda T: u + beta * math.log(max(1e-6, T * lam))
    return {2: p(2), 5: p(5), 10: p(10), 20: p(20), "_events": len(evs), "_beta": beta, "_lam": lam}

def design_flow(p_mm, psi=PSI, f=F_HA, v=V):
    """推理公式 Q = Psi*q*F; q = P/24 (mm/h 平均强度近似); 返回 m3/s 与初选管径 mm"""
    q = p_mm / 24.0
    q_m3s = psi * q * f * 10.0 / 3600.0          # mm/h->m/h(/1000), ha->m2(*10000), h->s(/3600)
    d_m = math.sqrt(4 * q_m3s / (math.pi * v)) if q_m3s > 0 else 0.0
    dn = next((d for d in DN if d >= d_m * 1000), DN[-1])
    return {"q_mmh": round(q, 2), "Q_m3s": round(q_m3s, 3), "D_mm": round(d_m * 1000), "DN": "DN%d" % dn}

def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    name, lat, lng = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

    qs = urllib.parse.urlencode({
        "latitude": lat, "longitude": lng, "timezone": "Asia/Shanghai",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "past_days": 90, "forecast_days": 7})
    d = fetch(API + "?" + qs)["daily"]

    n30 = len(d["time"]) - 7
    hist = [{"date": d["time"][i], "rain": d["precipitation_sum"][i] or 0.0} for i in range(n30)]
    fc   = [{"date": d["time"][i], "rain": d["precipitation_sum"][i] or 0.0} for i in range(n30, len(d["time"]))]

    rain = [x["rain"] for x in hist]
    total = sum(rain); mx = max(rain); mx_date = hist[rain.index(mx)]["date"]
    storm = sum(1 for r in rain if r >= 50); heavy = sum(1 for r in rain if 25 <= r < 50)
    wet = sum(1 for r in rain if r >= 0.1)
    streak = best = 0
    for r in rain:
        if r < 0.5: streak += 1; best = max(best, streak)
        else: streak = 0

    rp = return_periods(rain)
    df5 = design_flow(rp[5])

    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "%s_daily.csv" % name), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["date", "rainfall_mm"])
        for x in hist: w.writerow([x["date"], round(x["rain"], 1)])

    out = {
        "city": name, "lat": lat, "lng": lng, "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sample_days": len(hist), "window": [hist[0]["date"], hist[-1]["date"]],
        "stats": {"total_mm": round(total, 1), "max_day_mm": round(mx, 1), "max_date": mx_date,
                  "wet_days": wet, "heavy_days": heavy, "storm_days": storm, "max_dry_streak": best},
        "return_period_24h_mm": {k: round(v, 1) for k, v in rp.items() if isinstance(k, int)},
        "pot": {"threshold_mm": U, "events": rp["_events"], "beta": round(rp["_beta"], 2), "lambda_per_year": round(rp["_lam"], 2)},
        "design_flow_T5": {**df5, "psi": PSI, "area_ha": F_HA, "method": "Q = Psi*q*F, q = P5/24 (24h average approx)"},
        "forecast_7d_mm": round(sum(x["rain"] for x in fc), 1),
        "disclaimer": "基于近90天样本的初步估算; 正式设计须采用当地多年暴雨资料与当地暴雨强度公式 (GB50014-2021)。"
    }
    fn = "analysis_%s.json" % name
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("\n归档: data/%s_daily.csv  分析: %s" % (name, fn))

if __name__ == "__main__":
    main()
