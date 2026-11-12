"""
_quality_data.py - page10 品質異常根因分析的共用資料

特徵（與規格範例 batch_params=[180.5, 42.0, 15.2] 的順序一致）：
  temp 加熱溫度 (°C)、cooling 冷卻水流量 (L/min)、speed 軋延速度 (m/min)
標籤：0 = 良品、1 = 品質異常（不良）

資料來源（依序）：
  1. data/process_quality.csv   欄位 temp,cooling,speed,defect（defect 為 0/1）
  2. data/batches.csv           欄位 batch_id,temp,cooling,speed,yield_rate（yield_rate 為 0~1 的實測良率）
  3. 都不存在時，使用固定 seed 的「示範資料」：依我自訂的規則（溫度偏離 180°C、冷卻水流量偏低、
     軋延速度偏離 15 都會提高不良機率）合成。這個規則只是示範，不代表任何真實產線。
"""

import csv
import math
import os
import random

try:
    from ._common import default_output_path
except ImportError:
    from _common import default_output_path

FEATURES = ["temp", "cooling", "speed"]
LABELS = {"temp": "加熱溫度", "cooling": "冷卻水流量", "speed": "軋延速度"}
UNITS = {"temp": "°C", "cooling": "L/min", "speed": "m/min"}
HARD_LIMITS = {"temp": (0.0, 1500.0), "cooling": (0.0, 500.0), "speed": (0.0, 100.0)}
BATCH_ID_PATTERN = r"^B-\d{4}-\d{2}$"
DEFAULT_PARAMS = [180.5, 42.0, 15.2]


def clean_num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _defect_probability(temp, cooling, speed) -> float:
    """示範規則的真實不良機率（僅用來合成資料）。"""
    logit = (-5.0
             + 1.6 * ((temp - 180.0) / 6.0) ** 2
             + 2.6 * max(0.0, (42.0 - cooling) / 4.0)
             + 0.9 * ((speed - 15.0) / 1.2) ** 2)
    return 1.0 / (1.0 + math.exp(-logit))


def generate_samples(n: int = 600, seed: int = 11) -> list:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        temp = min(max(rng.gauss(180, 7), 160), 205)
        cooling = min(max(rng.gauss(42, 5), 26), 58)
        speed = min(max(rng.gauss(15, 1.4), 10.5), 19.5)
        defect = 1 if rng.random() < _defect_probability(temp, cooling, speed) else 0
        rows.append({"temp": round(temp, 2), "cooling": round(cooling, 2), "speed": round(speed, 2), "defect": defect})
    return rows


# 示範批次（手寫製程參數；沒有實測良率，趨勢圖畫的是模型估計良率）
DEMO_BATCHES = [
    ("B-2026-01", 180.2, 42.5, 15.1),
    ("B-2026-02", 179.4, 41.8, 14.8),
    ("B-2026-03", 181.0, 42.2, 15.4),
    ("B-2026-04", 182.0, 41.0, 15.0),
    ("B-2026-05", 180.8, 42.9, 15.3),
    ("B-2026-06", 178.5, 41.2, 14.5),
    ("B-2026-07", 183.6, 39.8, 15.6),
    ("B-2026-08", 185.0, 39.0, 15.8),
    ("B-2026-09", 187.0, 38.0, 15.9),
    ("B-2026-10", 189.5, 36.5, 16.3),
]


def _read_csv(path, needed):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(needed) <= set(reader.fieldnames):
            raise ValueError(f"{os.path.basename(path)} 欄位需包含 {needed}")
        for rec in reader:
            rows.append(rec)
    return rows


def load_samples():
    """回傳 (rows, source)。rows: [{temp,cooling,speed,defect}]"""
    path = default_output_path("process_quality.csv")
    if os.path.exists(path):
        try:
            rows = []
            for rec in _read_csv(path, FEATURES + ["defect"]):
                row = {k: float(rec[k]) for k in FEATURES}
                d = float(rec["defect"])
                if d not in (0.0, 1.0) or not all(math.isfinite(row[k]) for k in FEATURES):
                    raise ValueError("defect 只能是 0/1，特徵必須是有限數值")
                row["defect"] = int(d)
                rows.append(row)
            if len(rows) < 60 or len({r["defect"] for r in rows}) < 2:
                raise ValueError("至少需要 60 筆資料且良品與不良品都要有")
            return rows, "data/process_quality.csv"
        except Exception as e:
            print(f"讀取 process_quality.csv 失敗：{e}，改用示範資料", flush=True)
    return generate_samples(), "synthetic_demo (seed=11，示範規則非真實產線)"


def load_batches():
    """回傳 (batches, source)。batches: [{batch_id, params:[t,c,s], yield_rate(實測，示範資料為 None)}]（依 batch_id 排序）"""
    path = default_output_path("batches.csv")
    if os.path.exists(path):
        try:
            out = []
            for rec in _read_csv(path, ["batch_id"] + FEATURES + ["yield_rate"]):
                y = float(rec["yield_rate"])
                params = [float(rec[k]) for k in FEATURES]
                if not 0.0 <= y <= 1.0 or not all(math.isfinite(v) for v in params):
                    raise ValueError("yield_rate 需介於 0~1，特徵必須是有限數值")
                out.append({"batch_id": rec["batch_id"].strip(), "params": params, "yield_rate": y})
            if not out:
                raise ValueError("沒有資料列")
            out.sort(key=lambda b: b["batch_id"])
            return out, "data/batches.csv"
        except Exception as e:
            print(f"讀取 batches.csv 失敗：{e}，改用示範批次", flush=True)
    return ([{"batch_id": b[0], "params": [b[1], b[2], b[3]], "yield_rate": None} for b in DEMO_BATCHES],
            "demo_batches (手寫示範批次)")


def validate_params(params):
    """回傳 (clean_list or None, errors)。"""
    if not isinstance(params, (list, tuple)) or len(params) != len(FEATURES):
        return None, [f"batch_params 需要 {len(FEATURES)} 個數值（{', '.join(FEATURES)}）"]
    errors, vec = [], []
    for f, v in zip(FEATURES, params):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{LABELS[f]} 必須為數值")
        elif not math.isfinite(v):
            errors.append(f"{LABELS[f]} 不可為 NaN 或無限大")
        elif not HARD_LIMITS[f][0] <= v <= HARD_LIMITS[f][1]:
            errors.append(f"{LABELS[f]} = {v:g} 超出合理範圍 [{HARD_LIMITS[f][0]:g}, {HARD_LIMITS[f][1]:g}] {UNITS[f]}")
        else:
            vec.append(float(v))
    return (vec if not errors else None), errors
