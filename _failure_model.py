"""
_failure_model.py - skill_06 / skill_07 / skill_08 共用的突發故障邏輯迴歸模型

- 資料：優先讀 data/failure_history.csv（欄位 recency_days,alarms_90d,pressure,failed）；
        不存在時使用固定 seed 的「示範合成資料」（非真實設備紀錄）。
- 模型：邏輯迴歸，以 IRLS（牛頓法）+ 微量 L2 正則求解，特徵先 Z-Score 標準化。
- 評估：80/20 固定切分，AUC / Accuracy / Log-loss 皆為「測試集」結果。
- 僅使用 Python 標準庫。
"""

import csv
import math
import os
import random

try:
    from ._common import default_output_path
    from .skill_04_equipment_rul_prediction import solve_linear_system
except ImportError:
    from _common import default_output_path
    from skill_04_equipment_rul_prediction import solve_linear_system

FEATURES = ["recency_days", "alarms_90d", "pressure"]
FEATURE_LABELS = {
    "recency_days": "距上次維修天數",
    "alarms_90d": "近 90 天警報次數",
    "pressure": "運轉壓力",
}
FEATURE_UNITS = {"recency_days": "天", "alarms_90d": "次", "pressure": "MPa"}

# 物理合理範圍（超出直接攔截）
HARD_LIMITS = {
    "recency_days": (0.0, 1000.0),
    "alarms_90d": (0.0, 500.0),
    "pressure": (0.0, 30.0),
}
INTEGER_FEATURES = {"alarms_90d"}   # 警報次數必須是整數

BLOCK_Z = 4.0
WARN_Z = 3.0
MIN_AUC = 0.70
MIN_CLASS_COUNT = 10
TEST_RATIO = 0.20
SPLIT_SEED = 11
L2_LAMBDA = 1e-3
MAX_ITER = 50
TOL = 1e-8
PROB_EPS = 1e-6

# 示範合成資料的「真實」生成式（僅用於 demo 資料）
_DEMO_TRUE = {"intercept": -6.0, "recency_days": 0.020, "alarms_90d": 0.25, "pressure": 0.80}


# ---------- 基本函數 ----------
def sigmoid(z: float) -> float:
    """數值穩定的 Sigmoid。"""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def clean_num(v):
    """JSON 安全：非有限數值（NaN / inf）或非數值一律回傳 None。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


# ---------- 資料 ----------
def generate_reference_dataset(n: int = 1000, seed: int = 42) -> list:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        row = {
            "recency_days": rng.uniform(0, 180),
            "alarms_90d": float(min(40, int(rng.expovariate(1 / 9.0)))),
            "pressure": rng.uniform(0.8, 3.0),
        }
        z = _DEMO_TRUE["intercept"] + sum(_DEMO_TRUE[f] * row[f] for f in FEATURES)
        row["failed"] = 1 if rng.random() < sigmoid(z) else 0
        rows.append(row)
    return rows


def load_reference_dataset(csv_path: str = None):
    """回傳 (rows, source_label)。CSV 讀取失敗時退回示範資料，並在標籤中註明。"""
    path = csv_path or default_output_path("failure_history.csv")
    if os.path.exists(path):
        try:
            rows = []
            needed = FEATURES + ["failed"]
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or not set(needed) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {needed}")
                for rec in reader:
                    row = {k: float(rec[k]) for k in needed}
                    if row["failed"] not in (0.0, 1.0):
                        raise ValueError("failed 欄位只能是 0 或 1")
                    row["failed"] = int(row["failed"])
                    rows.append(row)
            if len(rows) < 50:
                raise ValueError(f"資料僅 {len(rows)} 筆，至少需要 50 筆")
            return rows, "data/failure_history.csv"
        except Exception as e:
            print(f"讀取 failure_history.csv 失敗：{e}，改用示範合成資料", flush=True)
    return generate_reference_dataset(), "synthetic_demo (seed=42)"


# ---------- 輸入驗證 ----------
def validate_inputs(raw: dict):
    """回傳 (values_dict | None, errors)。"""
    values, errors = {}, []
    for f in FEATURES:
        v = raw.get(f)
        label = FEATURE_LABELS[f]
        if v is None:
            errors.append(f"缺少欄位 {f}")
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{label} 必須為數值")
            continue
        if not math.isfinite(v):
            errors.append(f"{label} 不可為 NaN 或無限大")
            continue
        lo, hi = HARD_LIMITS[f]
        if not lo <= v <= hi:
            errors.append(f"{label} = {v:g} 超出合理範圍 [{lo:g}, {hi:g}] {FEATURE_UNITS[f]}")
            continue
        if f in INTEGER_FEATURES and float(v) != int(v):
            errors.append(f"{label} 必須為整數（收到 {v:g}）")
            continue
        values[f] = float(v)
    return (values if not errors else None), errors


# ---------- 標準化 ----------
def compute_stats(rows: list) -> dict:
    stats = {}
    for f in FEATURES:
        vals = [r[f] for r in rows]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        std = math.sqrt(var)
        if std <= 0:
            raise ValueError(f"特徵 {f} 標準差為 0，無法標準化")
        stats[f] = {"mean": mean, "std": std, "min": min(vals), "max": max(vals)}
    return stats


def zscores(values: dict, stats: dict) -> dict:
    return {f: (values[f] - stats[f]["mean"]) / stats[f]["std"] for f in FEATURES}


def check_extrapolation(values: dict, stats: dict):
    """回傳 (warnings, blocked_reasons)。"""
    warnings, blocked = [], []
    for f in FEATURES:
        s = stats[f]
        z = (values[f] - s["mean"]) / s["std"]
        label = f"{FEATURE_LABELS[f]}={values[f]:g}{FEATURE_UNITS[f]}"
        if abs(z) > BLOCK_Z:
            blocked.append(f"{label} 的 |z|={abs(z):.2f} > {BLOCK_Z:g}，遠離訓練資料範圍")
        elif values[f] < s["min"] or values[f] > s["max"]:
            warnings.append(f"{label} 超出訓練資料範圍 [{s['min']:.1f}, {s['max']:.1f}]，預測屬外插，可信度下降")
        elif abs(z) > WARN_Z:
            warnings.append(f"{label} 的 |z|={abs(z):.2f} > {WARN_Z:g}")
    return warnings, blocked


# ---------- 邏輯迴歸（IRLS / 牛頓法）----------
def fit_logistic(X: list, y: list, l2: float = L2_LAMBDA, max_iter: int = MAX_ITER, tol: float = TOL):
    """
    X 不含截距欄。回傳 (beta, iterations, converged)，beta = [截距, b1, b2, ...]。
    截距不做正則；牛頓更新：β ← β + (XᵀWX + λI)⁻¹ (Xᵀ(y-p) - λβ)
    """
    Xa = [[1.0] + list(r) for r in X]
    p_dim = len(Xa[0])
    beta = [0.0] * p_dim
    for it in range(1, max_iter + 1):
        probs = [sigmoid(sum(b * x for b, x in zip(beta, row))) for row in Xa]
        grad = [sum(row[j] * (yi - pi) for row, yi, pi in zip(Xa, y, probs)) - (l2 * beta[j] if j else 0.0)
                for j in range(p_dim)]
        H = [[0.0] * p_dim for _ in range(p_dim)]
        for row, pi in zip(Xa, probs):
            w = max(pi * (1 - pi), 1e-9)
            for i in range(p_dim):
                wi = w * row[i]
                for j in range(p_dim):
                    H[i][j] += wi * row[j]
        for j in range(1, p_dim):
            H[j][j] += l2
        step = solve_linear_system(H, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < tol:
            return beta, it, True
    return beta, max_iter, False


# ---------- 評估指標 ----------
def auc_score(probs: list, labels: list) -> float:
    """Mann-Whitney U 形式的 AUC，同分取平均名次。任一類別為空時回傳 0.5。"""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = sorted(range(len(probs)), key=lambda i: probs[i])
    ranks = [0.0] * len(probs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and probs[order[j + 1]] == probs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum_pos = sum(r for r, l in zip(ranks, labels) if l == 1)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def log_loss(probs: list, labels: list) -> float:
    total = 0.0
    for p, y in zip(probs, labels):
        p = min(max(p, PROB_EPS), 1 - PROB_EPS)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(probs)


# ---------- 完整模型 ----------
def fit_failure_model(csv_path: str = None) -> dict:
    rows, source = load_reference_dataset(csv_path)

    idx = list(range(len(rows)))
    random.Random(SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * TEST_RATIO))
    test = [rows[i] for i in idx[:n_test]]
    train = [rows[i] for i in idx[n_test:]]

    n_pos_train = sum(r["failed"] for r in train)
    n_neg_train = len(train) - n_pos_train
    if n_pos_train < MIN_CLASS_COUNT or n_neg_train < MIN_CLASS_COUNT:
        raise ValueError(
            f"訓練集故障 {n_pos_train} 筆 / 正常 {n_neg_train} 筆，任一類別少於 {MIN_CLASS_COUNT} 筆，無法穩定擬合")

    stats = compute_stats(train)
    X_train = [[zscores(r, stats)[f] for f in FEATURES] for r in train]
    y_train = [r["failed"] for r in train]
    beta, iters, converged = fit_logistic(X_train, y_train)

    def prob_of(row):
        z = zscores(row, stats)
        return sigmoid(beta[0] + sum(beta[i + 1] * z[f] for i, f in enumerate(FEATURES)))

    test_probs = [prob_of(r) for r in test]
    test_labels = [r["failed"] for r in test]
    acc = sum((1 if p >= 0.5 else 0) == y for p, y in zip(test_probs, test_labels)) / len(test)

    std_coefs = {f: beta[i + 1] for i, f in enumerate(FEATURES)}
    raw_coefs = {f: std_coefs[f] / stats[f]["std"] for f in FEATURES}
    raw_intercept = beta[0] - sum(std_coefs[f] * stats[f]["mean"] / stats[f]["std"] for f in FEATURES)

    return {
        "source": source, "stats": stats, "intercept_z": beta[0], "std_coefs": std_coefs,
        "raw_coefs": raw_coefs, "raw_intercept": raw_intercept,
        "iterations": iters, "converged": converged,
        "test_probs": test_probs, "test_labels": test_labels,
        "metrics": {
            "auc": auc_score(test_probs, test_labels), "accuracy": acc,
            "log_loss": log_loss(test_probs, test_labels),
            "n_train": len(train), "n_test": len(test),
            "prevalence_train": n_pos_train / len(train),
            "n_pos_test": sum(test_labels), "n_neg_test": len(test_labels) - sum(test_labels),
        },
    }


def linear_score(model: dict, values: dict) -> float:
    """z = wᵀx + b（以標準化特徵計算）。"""
    z = zscores(values, model["stats"])
    return model["intercept_z"] + sum(model["std_coefs"][f] * z[f] for f in FEATURES)
