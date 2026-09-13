# -*- coding: utf-8 -*-
"""
项目自检脚本 (verify.py)
========================
用法:  python verify.py

分四部分：
  A. index.html 静态断言（版号 / 分隔符兼容 / 城市数 / 竞态守卫 / 免责声明）
  B. GitHub Actions workflow 校验（YAML / cron / 权限 / 坐标与前端一致）
  C. 双端数值交叉验证（index.html 里的 JS 算法 vs Python 同公式，用 node 执行对比）
  D. 数据文件完整性（data/*.csv 行数与最新日期）

仅依赖 Python 标准库 + 本机 node（用于 C 部分）。
"""
import os, re, sys, glob, json, math, subprocess, tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(ROOT, 'index.html')
WF = os.path.join(ROOT, '.github', 'workflows', 'daily-data-update.yml')

results = []


def chk(name, ok, extra=''):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{extra}]" if extra else ''))


html = open(HTML, encoding='utf-8').read()

# ---------- A. index.html 静态断言 ----------
chk('版号为 v2.4 移动提速版', 'v2.4 移动提速版' in html)
chk('分隔符兼容全角 ｜ ／', 'replace(/[｜]/g' in html and 'replace(/[／]/g' in html)
chk('分隔符主用 /', 'split(/[/|]/)' in html)
chk('城市选项 ≥16', len(re.findall(r'<option value="[^"]+\|[0-9.]+\|[0-9.]+"', html)) >= 16)
chk('竞态守卫 loadSeq', 'loadSeq' in html)
chk('导出免责声明为近 5 年', '近5年历史样本' in html)
chk('ECharts 四级降级加载', 'cdn.staticfile.org/echarts' in html and 'vendor/echarts.min.js' in html)
chk('render 等待 ECharts 就绪', 'if(!window.echarts)' in html)

# ---------- B. workflow 校验（零依赖；装了 pyyaml 则追加语法校验） ----------
if os.path.exists(WF):
    wf = open(WF, encoding='utf-8').read()
    chk('workflow 每日定时', bool(re.search(r"cron:\s*'0 22 \* \* \*'", wf)))
    chk('workflow 支持手动触发', 'workflow_dispatch:' in wf)
    chk('workflow 写权限', 'contents: write' in wf)
    cmds = re.findall(r'python (\S+\.py) (\S+) ([\d.]+) ([\d.]+)', wf)
    chk('采集城市数 = 3', len(cmds) == 3)
    chk('坐标与前端一致', all(f'{n}|{lat}|{lng}' in html for _, n, lat, lng in cmds))
    chk('仅变更时提交', 'diff --cached --quiet' in wf)
    try:
        import yaml
        yaml.safe_load(wf)          # YAML 1.1 会把 `on:` 读成 True，仅校验语法
        chk('workflow YAML 语法有效', True)
    except ImportError:
        pass                        # 可选：uv run --with pyyaml python verify.py
    except Exception as e:
        chk('workflow YAML 语法有效', False, str(e)[:60])
else:
    chk('workflow 文件存在', False)


# ---------- C. 双端数值交叉验证 ----------
def py_return_periods(rain, u=5.0):
    """与 index.html 的 returnPeriods 同公式：x_T = u + β·ln(T·λ)"""
    evs = [r for r in rain if r >= u]
    beta = sum(r - u for r in evs) / len(evs) if evs else 0.0
    n_yr = max(len(rain) / 365.25, 1e-6)
    lam = len(evs) / n_yr
    p = lambda T: u + beta * math.log(max(1e-6, T * lam))
    return {'p2': p(2), 'p5': p(5), 'p10': p(10), 'p20': p(20), 'events': len(evs), 'beta': beta, 'lam': lam}


# 固定测试序列（确定性，无网络依赖）：含 6 场 ≥5mm 事件
RAIN = [0, 0, 2.1, 7.5, 0, 0, 12.3, 0, 5.0, 0, 0, 0, 21.4, 0, 3.2, 0, 0, 8.8, 0, 0,
        0.4, 0, 0, 6.6, 0, 0, 0, 15.1, 0, 0]


def extract_js_fn(name):
    m = re.search(r'function ' + name + r'\([^\n]*\n(?:.*?\n)?\}', html, re.S)
    return m.group(0) if m else None


fn_rp = extract_js_fn('returnPeriods')
fn_df = extract_js_fn('designFlow')
chk('提取到 JS 算法函数', bool(fn_rp and fn_df))

if fn_rp and fn_df:
    js = (
        fn_rp + '\n' + fn_df + '\n'
        f'const rain = {json.dumps(RAIN)};\n'
        'const rp = returnPeriods(rain);\n'
        'const df = designFlow(rp.p5, 0.6, 5);\n'
        'console.log(JSON.stringify({rp, df}));\n'
    )
    tmpf = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
    tmpf.write(js); tmpf.close()
    try:
        out = subprocess.run(['node', tmpf.name], capture_output=True, text=True,
                             timeout=30, encoding='utf-8')
        js_res = json.loads(out.stdout)
    except Exception as e:
        js_res = None
        chk('node 执行 JS 算法', False, str(e)[:60])
    finally:
        os.unlink(tmpf.name)

    if js_res:
        py_res = py_return_periods(RAIN)
        for k in ('p2', 'p5', 'p10', 'p20', 'beta', 'lam'):
            same = abs(py_res[k] - js_res['rp'][k]) < 1e-9
            chk(f'交叉 {k}: Python={py_res[k]:.6f} JS={js_res["rp"][k]:.6f}', same)
        chk('交叉 events 一致', py_res['events'] == js_res['rp']['events'],
            f"py={py_res['events']} js={js_res['rp']['events']}")
        chk('交叉 Q 一致 (Q=ΨqF)',
            abs(js_res['df']['Q'] - round((0.6 * js_res['rp']['p5'] / 24) * 5 * 10 / 3600, 3)) < 1e-9)

# ---------- D. 数据文件完整性 ----------
csvs = sorted(glob.glob(os.path.join(ROOT, 'data', '*_daily.csv')))
chk('data/*.csv 存在', len(csvs) >= 1, f'{len(csvs)} 个')
for c in csvs:
    rows = open(c, encoding='utf-8-sig').read().strip().splitlines()
    name = os.path.basename(c)
    chk(f'{name} 行数正常(>1000)', len(rows) > 1000, f'{len(rows)} 行, 最新 {rows[-1].split(",")[0]}')

failed = [n for n, ok in results if not ok]
print('\n' + '=' * 50)
print(f'总计 {len(results)} 项, 通过 {len(results) - len(failed)}, 失败 {len(failed)}')
print('结论: ALL PASSED' if not failed else f'失败项: {failed}')
sys.exit(1 if failed else 0)
