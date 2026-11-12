"""
_spc_data.py - page12 製程參數資料與標準化（skill_20 / 21 / 22 與 /api/spc-clustering 共用）

欄位：temp 製程溫度 (°C)、pressure 製程壓力 (MPa)；列順序即時間順序（SPC 管制圖需要時間順序）。

資料來源（依序）：
  1. data/process_params.csv   欄位 temp,pressure（依時間排列）
  2. 不存在時使用固定 seed 的示範資料：300 筆，三種運轉模式（隨機交錯，模擬不同配方的批次）
     加上 4 個人為注入的尖峰點。這是示範用的假想資料，不是真實產線量測。

標準化：z = (x - mean) / std，std 用樣本標準差（n-1），平均與標準差都用全部資料計算。
"""

import csv
import math
import os
import random

try:
    from ._common import default_output_path
except ImportError:
    from _common import default_output_path

COLUMNS = ["temp", "pressure"]
Z_NAMES = {"temp": "temp_z", "pressure": "press_z"}
LABELS = {"temp": "製程溫度", "pressure": "製程壓力"}
UNITS = {"temp": "°C", "pressure": "MPa"}
MAX_ROWS = 5000
MIN_ROWS = 30


def clean_num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def generate_demo(n: int = 300, seed: int = 8):
    rng = random.Random(seed)
    modes = [((178.0, 1.80), 0.40), ((186.0, 2.30), 0.35), ((172.0, 2.60), 0.25)]
    rows = []
    for _ in range(n):
        r, acc = rng.random(), 0.0
        mu = modes[-1][0]
        for m, p in modes:
            acc += p
            if r <= acc:
                mu = m
                break
        rows.append({"temp": round(rng.gauss(mu[0], 2.0), 2), "pressure": round(rng.gauss(mu[1], 0.12), 3)})
    for i, (dt, dp) in {47: (16.0, 0.0), 123: (0.0, 1.0), 201: (-15.0, 0.0), 268: (14.0, 0.9)}.items():
        rows[i]["temp"] = round(rows[i]["temp"] + dt, 2)
        rows[i]["pressure"] = round(rows[i]["pressure"] + dp, 3)
    return rows


def load_data():
    """回傳 (rows, source)。"""
    path = default_output_path("process_params.csv")
    if os.path.exists(path):
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or not set(COLUMNS) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {COLUMNS}")
                for rec in reader:
                    row = {c: float(rec[c]) for c in COLUMNS}
                    if not all(math.isfinite(v) for v in row.values()):
                        raise ValueError("數值必須是有限數字")
                    rows.append(row)
            if not MIN_ROWS <= len(rows) <= MAX_ROWS:
                raise ValueError(f"資料筆數需介於 {MIN_ROWS}–{MAX_ROWS}（純 Python 的效能上限），目前 {len(rows)}")
            return rows, "data/process_params.csv"
        except Exception as e:
            print(f"讀取 process_params.csv 失敗：{e}，改用示範資料", flush=True)
    return generate_demo(), "synthetic_demo (seed=8，示範資料非真實產線量測)"


def standardize(rows, columns):
    """回傳 (Z 矩陣, stats)。stats[col] = {mean, std}；某欄標準差為 0 會拋出 ValueError。"""
    stats = {}
    for c in columns:
        vals = [r[c] for r in rows]
        m = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
        if sd <= 0:
            raise ValueError(f"{LABELS[c]} 的標準差為 0（所有值相同），無法標準化")
        stats[c] = {"mean": m, "std": sd}
    Z = [[(r[c] - stats[c]["mean"]) / stats[c]["std"] for c in columns] for r in rows]
    return Z, stats


def validate_matrix(data, name="data", min_rows=1):
    """檢查 list[list[float]]：矩形、有限數值、至少 min_rows 列。回傳 (清理後矩陣 or None, 錯誤清單)。"""
    if not isinstance(data, (list, tuple)) or not data:
        return None, [f"{name} 必須是非空的二維數值陣列"]
    if len(data) > MAX_ROWS:
        return None, [f"{name} 共 {len(data)} 筆，超過上限 {MAX_ROWS}（純 Python 的效能限制），請先抽樣"]
    dim = None
    out = []
    for i, row in enumerate(data):
        if not isinstance(row, (list, tuple)) or not row:
            return None, [f"{name} 第 {i + 1} 列不是數值陣列"]
        if dim is None:
            dim = len(row)
        if len(row) != dim:
            return None, [f"{name} 各列維度不一致（第 {i + 1} 列有 {len(row)} 個值，應為 {dim}）"]
        for v in row:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None, [f"{name} 第 {i + 1} 列含有非數值"]
            if not math.isfinite(v):
                return None, [f"{name} 第 {i + 1} 列含有 NaN 或無限大"]
        out.append([float(v) for v in row])
    if len(out) < min_rows:
        return None, [f"{name} 至少需要 {min_rows} 筆，目前 {len(out)} 筆"]
    return out, []


def column_std_warnings(X, tol=0.5):
    """K-Means 對尺度敏感：欄位標準差明顯偏離 1（不是 z 分數）時回傳警告。"""
    warns = []
    n, d = len(X), len(X[0])
    for j in range(d):
        col = [r[j] for r in X]
        m = sum(col) / n
        sd = math.sqrt(sum((v - m) ** 2 for v in col) / max(1, n - 1))
        if abs(sd - 1) > tol or abs(m) > tol:
            warns.append(f"第 {j + 1} 欄不像 z 分數（平均 {m:.2f}、標準差 {sd:.2f}），K-Means 的距離會被尺度大的欄位主導，請先標準化")
    return warns
