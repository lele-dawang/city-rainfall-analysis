# -*- coding: utf-8 -*-
"""
城市降雨数据采集与排水分析管线 (v3)
=====================================
数据源:
  - 历史: Open-Meteo Archive API (ERA5 再分析, 1940 至今, 默认取近 5 年)
  - 预报: Open-Meteo Forecast API (未来 7 天)
方法:
  1. 采集近 N 年(默认5年)逐日降雨 + 未来 7 天预报
  2. 基础统计: 近90天累计/最大/大雨日/暴雨日/连续无雨 + 全历史概况
  3. 设计暴雨重现期估算: 超阈值法(POT) + 指数分布 x_T = u + beta*ln(T*lambda)
     —— 基于多年样本, 比 90 天样本可靠得多
  4. 雨水设计流量估算: 推理公式 Q = Psi*q*F (q 取 T 年重现期 24h 平均强度)
  5. 归档: data/<城市>_daily.csv (全历史) + analysis_<城市>.json

用法:
  python fetch_rain.py 张家口 40.768 114.886 [年数=5]
依赖: 仅 Python 标准库
"""
import sys, json, math, csv, os, datetime
import urllib.request, urllib.parse

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
U = 5.0          # POT 阈值 mm（日降雨 >= 5mm 视为一场独立降雨事件）
PSI = 0.6        # 径流系数（绿地/道路混合，参考 GB50014）
F_HA = 5.0       # 汇水面积 ha（示例小区）
V = 1.0          # 满流圆管初选流速 m/s
DN = [75, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200]

def fetch(url, timeout=30, retries=4):
    """带重试的 GET（国内网络 TLS 偶发重置，重试可显著提高成功率）"""
    import time
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RainfallAnalysis/3.0 (student project)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def return_periods(rain, u=U):
    """超阈值法 + 指数分布: {T: 24h设计雨量mm} + 过程参数"""
    evs = [r for r in rain if r >= u]
    beta = sum(r - u for r in evs) / len(evs) if evs else 0.0
    ny = max(len(rain) / 365.25, 1e-6)
    lam = len(evs) / ny
    p = lambda T: u + beta * math.log(max(1e-6, T * lam))
    return {2: p(2), 5: p(5), 10: p(10), 20: p(20),
            "_events": len(evs), "_beta": beta, "_lam": lam, "_years": ny}

def design_flow(p_mm, psi=PSI, f=F_HA, v=V):
    """推理公式 Q = Psi*q*F; q = P/24 (mm/h 平均强度近似); 返回 m3/s 与初选管径 mm"""
    q = p_mm / 24.0
    q_m3s = psi * q * f * 10.0 / 3600.0
    d_m = math.sqrt(4 * q_m3s / (math.pi * v)) if q_m3s > 0 else 0.0
    dn = next((d for d in DN if d >= d_m * 1000), DN[-1])
    return {"q_mmh": round(q, 1), "Q_m3s": round(q_m3s, 3), "D_mm": round(d_m * 1000), "DN": "DN%d" % dn}

def stats(hist):
    rain = [x["rain"] for x in hist]
    total = sum(rain)
    mx = max(rain) if rain else 0
    mx_date = hist[rain.index(mx)]["date"] if rain else ""
    storm = sum(1 for r in rain if r >= 50)
    heavy = sum(1 for r in rain if 25 <= r < 50)
    wet = sum(1 for r in rain if r >= 0.1)
    streak = best = 0
    for r in rain:
        if r < 0.5:
            streak += 1; best = max(best, streak)
        else:
            streak = 0
    return {"total_mm": round(total, 1), "max_day_mm": round(mx, 1), "max_date": mx_date,
            "wet_days": wet, "heavy_days": heavy, "storm_days": storm, "max_dry_streak": best}

def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    name, lat, lng = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    years = int(sys.argv[4]) if len(sys.argv) > 4 else 5

    today = datetime.date.today()
    start = today - datetime.timedelta(days=int(years * 365.25))
    q_arch = urllib.parse.urlencode({
        "latitude": lat, "longitude": lng, "timezone": "Asia/Shanghai",
        "start_date": start.isoformat(), "end_date": (today - datetime.timedelta(days=1)).isoformat(),
        "daily": "precipitation_sum"})
    q_fc = urllib.parse.urlencode({
        "latitude": lat, "longitude": lng, "timezone": "Asia/Shanghai",
        "daily": "precipitation_sum", "forecast_days": 7})

    a = fetch(ARCHIVE + "?" + q_arch)["daily"]
    f = fetch(FORECAST + "?" + q_fc)["daily"]

    hist = [{"date": a["time"][i], "rain": a["precipitation_sum"][i] or 0.0} for i in range(len(a["time"]))]
    fc = [{"date": f["time"][i], "rain": f["precipitation_sum"][i] or 0.0} for i in range(len(f["time"]))]

    rain_all = [x["rain"] for x in hist]
    rp = return_periods(rain_all)
    df5 = design_flow(rp[5])
    s90 = stats(hist[-90:])
    s_all = stats(hist)

    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "%s_daily.csv" % name), "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp); w.writerow(["date", "rainfall_mm"])
        for x in hist:
            w.writerow([x["date"], round(x["rain"], 1)])

    out = {
        "city": name, "lat": lat, "lng": lng, "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sample_years": round(rp["_years"], 1), "sample_days": len(hist),
        "window": [hist[0]["date"], hist[-1]["date"]],
        "stats_90d": s90, "stats_history": s_all,
        "return_period_24h_mm": {k: round(v, 1) for k, v in rp.items() if isinstance(k, int)},
        "pot": {"threshold_mm": U, "events": rp["_events"], "beta": round(rp["_beta"], 2), "lambda_per_year": round(rp["_lam"], 2)},
        "design_flow_T5": {**df5, "psi": PSI, "area_ha": F_HA, "method": "Q = Psi*q*F, q = P5/24 (24h average approx)"},
        "forecast_7d_mm": round(sum(x["rain"] for x in fc), 1),
        "disclaimer": "基于近 %d 年历史数据(ERA5 再分析)的估算; 正式设计仍须采用当地多年暴雨资料与当地暴雨强度公式 (GB50014-2021)。" % round(rp["_years"])
    }
    fn = "analysis_%s.json" % name
    with open(fn, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("\n归档: data/%s_daily.csv (%d 天)   分析: %s" % (name, len(hist), fn))

if __name__ == "__main__":
    main()
