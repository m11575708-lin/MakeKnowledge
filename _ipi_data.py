"""
_ipi_data.py - page13 智慧生產指數預測的資料與特徵建構（skill_23 與 /api/index-forecast 共用）

月度資料欄位：month (YYYY-MM)、ipi 工業生產指數、export_orders 出口訂單指數、utilization 設備稼動率 (%)

資料來源（依序）：
  1. data/ipi_monthly.csv   欄位 month,ipi,export_orders,utilization（依時間排列）
  2. 不存在時使用固定 seed 的示範資料（120 個月，2016-01 起）。
     這是我設計的合成資料，不是任何真實統計：
       潛在景氣 a_t 為 AR(1)；IPI = 趨勢 + 季別效應 + 2.0·a_t + 雜訊；
       稼動率反映當月景氣；出口訂單帶有「領先一個月」的景氣資訊（領先指標）。
     因此模型「有東西可以學」，但這是我埋進去的結構，不代表真實景氣的規律。

預測設計（直接多步預測，避免遞迴預測需要未來外生變數）：
  對 h = 1、2、3（未來三個月 = 下一季），各訓練一個 MLP，預測「變化量」Δ_h = IPI(t+h) − IPI(t)。
  預測變化量而非水準，是因為 IPI 有長期上升趨勢，MLP 在訓練範圍外外推能力差；
  此時「延續上月」基準就等於預測 Δ = 0，比較公平。
特徵（時間 t 當下已知）：
  ipi    → IPI 1 個月變化、3 個月變化
  export → 出口訂單 1 個月變化
  util   → 稼動率水準
  season → 目標月與當月所屬季別 dummy（Q2、Q3、Q4，Q1 為基準，共 6 欄）
"""

import csv
import math
import os
import random

try:
    from ._common import default_output_path
except ImportError:
    from _common import default_output_path

FEATURE_KEYS = ["ipi", "export", "util", "season"]
FEATURE_LABELS = {"ipi": "IPI 歷史變化", "export": "出口訂單", "util": "設備稼動率", "season": "季節變數"}
HORIZONS = (1, 2, 3)
MIN_MONTHS = 60
MAX_MONTHS = 600
MIN_IPI, MAX_IPI = 1.0, 1000.0
_SEASON = {1: -2.0, 2: 0.5, 3: 1.0, 4: 0.5}     # 示範資料的季別效應（Q1~Q4）


def clean_num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def quarter(month_of_year: int) -> int:
    return (month_of_year - 1) // 3 + 1


def month_label(start_year: int, start_month: int, offset: int) -> str:
    idx = start_year * 12 + (start_month - 1) + offset
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def generate_demo(n: int = 120, seed: int = 13):
    rng = random.Random(seed)
    a = 0.0
    etas, acts = [], []
    for _ in range(n + 1):
        eta = rng.gauss(0, 1.0)
        a = 0.85 * a + eta
        etas.append(eta)
        acts.append(a)
    rows = []
    for t in range(n):
        m = t % 12 + 1
        q = quarter(m)
        ipi = 100 + 0.22 * t + _SEASON[q] + 2.0 * acts[t] + rng.gauss(0, 0.6)
        util = 78 + 2.2 * acts[t] + (1.0 if q in (2, 3) else -0.5) + rng.gauss(0, 0.8)
        exp = 100 + 0.3 * t + 2.0 * etas[t + 1] + 2.0 * acts[t] * 0.3 + rng.gauss(0, 1.0)
        rows.append({"month": month_label(2016, 1, t), "ipi": round(ipi, 2),
                     "export_orders": round(exp, 2), "utilization": round(util, 2)})
    return rows


def load_data():
    """回傳 (rows, source)。"""
    path = default_output_path("ipi_monthly.csv")
    if os.path.exists(path):
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                need = ["month", "ipi", "export_orders", "utilization"]
                if not reader.fieldnames or not set(need) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {need}")
                for rec in reader:
                    mo = rec["month"].strip()
                    y, m = mo.split("-")
                    if not (1 <= int(m) <= 12):
                        raise ValueError(f"月份格式錯誤：{mo}")
                    row = {"month": f"{int(y):04d}-{int(m):02d}", "ipi": float(rec["ipi"]),
                           "export_orders": float(rec["export_orders"]), "utilization": float(rec["utilization"])}
                    if not all(math.isfinite(row[k]) for k in need[1:]):
                        raise ValueError("數值必須是有限數字")
                    rows.append(row)
            if not MIN_MONTHS <= len(rows) <= MAX_MONTHS:
                raise ValueError(f"資料筆數需介於 {MIN_MONTHS}–{MAX_MONTHS} 個月，目前 {len(rows)}")
            return rows, "data/ipi_monthly.csv"
        except Exception as e:
            print(f"讀取 ipi_monthly.csv 失敗：{e}，改用示範資料", flush=True)
    return generate_demo(), "synthetic_demo (seed=13，示範資料非真實統計)"


def build_samples(ipi, exp, util, start_month, feats, h):
    """回傳 (時間索引 t 清單, X, y)。y = IPI(t+h) − IPI(t)。需要 t ≥ 3 與 t + h ≤ n − 1。"""
    n = len(ipi)
    ts, X, y = [], [], []
    for t in range(3, n - h):
        ts.append(t)
        X.append(feature_vector(ipi, exp, util, start_month, feats, t, h))
        y.append(ipi[t + h] - ipi[t])
    return ts, X, y


def feature_vector(ipi, exp, util, start_month, feats, t, h):
    x = []
    if "ipi" in feats:
        x += [ipi[t] - ipi[t - 1], ipi[t] - ipi[t - 3]]
    if "export" in feats:
        x += [exp[t] - exp[t - 1]]
    if "util" in feats:
        x += [util[t]]
    if "season" in feats:
        qt = quarter((start_month - 1 + t + h) % 12 + 1)
        qc = quarter((start_month - 1 + t) % 12 + 1)
        x += [1.0 if qt == q else 0.0 for q in (2, 3, 4)] + [1.0 if qc == q else 0.0 for q in (2, 3, 4)]
    return x


def feature_names(feats):
    out = []
    if "ipi" in feats:
        out += ["IPI 1月變化", "IPI 3月變化"]
    if "export" in feats:
        out += ["出口訂單 1月變化"]
    if "util" in feats:
        out += ["稼動率"]
    if "season" in feats:
        out += ["目標季=Q2", "目標季=Q3", "目標季=Q4", "當季=Q2", "當季=Q3", "當季=Q4"]
    return out
