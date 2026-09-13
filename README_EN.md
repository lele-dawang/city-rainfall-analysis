# 🌧 City Rainfall Analysis & Drainage Design Dashboard

**English** | [中文](README.md)

An open-source dashboard that turns public climate data into **rainfall statistics and drainage design calculations** for cities — built as a water supply & drainage engineering student project.

> **Why it's different**: most "rain" visualizations just show weather. This one goes one step further — it estimates **design storm rainfall for return periods** (2/5/10/20 years) from 5 years of ERA5 reanalysis data, and computes **stormwater design flow** using the rational method `Q = Ψ·q·F` per Chinese standard **GB50014-2021**.

## 🔗 Live Demo

**https://yushuiqing.surge.sh** — interactive, mobile friendly, no sign-up. (Backup: [GitHub Pages](https://lele-dawang.github.io/city-rainfall-analysis/))

## Features

- **Real data pipeline** — Python (standard library only) fetches 5 years of daily rainfall (ERA5 reanalysis) + 7-day forecast from [Open-Meteo](https://open-meteo.com) (free, no API key), archives CSV/JSON, fully reproducible
- **Design storm return periods** — peaks-over-threshold (POT) sampling + exponential distribution fitting: `x_T = u + β·ln(T·λ)`
- **Stormwater design flow** — rational method `Q = Ψ·q·F` with interactive runoff coefficient / catchment area / return period, auto-selects pipe diameter (full-flow circular pipe, n=0.013, v=1.0 m/s)
- **Interactive visualization** — ECharts: daily rainfall, return-period curve, 7-day forecast, hourly rainfall; export JSON/CSV
- **Fast loading architecture** — 90-day data renders instantly, 5-year history upgrades in the background (6h cache, mobile/weak-network friendly)
- **Cross-validated** — Python pipeline and frontend JavaScript produce identical results, verified by an automated self-check script (`verify.py`, 29 assertions)
- **Automated daily updates** — GitHub Actions refreshes the data every day, no local machine required
- **16 cities included** + custom coordinates (supports `City/Lat/Lng` input)

## Methods & Assumptions (stated honestly)

| Step | Method | Basis |
|---|---|---|
| Data sample | ~5 years daily rainfall (ERA5 reanalysis, archive API) | freely available back to 1940 |
| Return period | POT (u = 5 mm) + exponential fit `x_T = u + β·ln(T·λ)` | common extreme-value simplification |
| Design rainfall | `q = P_T / 24` (24 h mean intensity approximation) | simplified; formal design uses local intensity–duration–frequency formula |
| Design flow | Rational method `Q = Ψ·q·F` | GB50014-2021 *Outdoor Drainage Design Standard* |
| Pipe selection | full-flow circular pipe, n = 0.013, v = 1.0 m/s | typical design velocity |

**Limitation**: results based on a ~5-year sample are for **learning and demonstration** only (long return periods such as 20-year require longer records). Formal design must use ≥20 years of local rainfall records and the local design storm formula.

## Quick Start

```bash
# Fetch & analyze any city (name latitude longitude [years, default 5])
python fetch_rain.py Beijing 39.904 116.407 5

# Run the self-check (frontend assertions + Python/JS cross-validation)
python verify.py
```

Open `index.html` directly, or visit the live demo. Pick a city from the dropdown or type custom coordinates.

## Project Structure

```
├── index.html        # Single-file frontend (ECharts via multi-CDN with local fallback)
├── fetch_rain.py     # Data pipeline & analysis (Python stdlib only)
├── verify.py         # Self-check: static assertions + Python/JS cross-validation
├── .github/workflows/daily-data-update.yml   # Automated daily data refresh
├── vendor/           # Locally bundled ECharts (slim build, CDN fallback)
├── data/             # Archived daily rainfall CSV
└── analysis_*.json   # Analysis reports
```

## Tech Stack

Python (urllib/json/csv, no third-party deps) · HTML/CSS/JS · ECharts 5 · Open-Meteo API · surge.sh · GitHub Actions

## Data & License

Data source: [Open-Meteo](https://open-meteo.com) (CC BY 4.0) — please keep the attribution.

© 2026 乐乐大王 (Lele Dawang). Personal learning project — **non-commercial use only unless authorized**.
