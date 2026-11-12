# -*- coding: utf-8 -*-
"""
failure_core.py — Skill 06 / 07 / 08 共用的「突發故障風險」邏輯迴歸核心（純標準庫）

職責：
  1. 載入訓練資料：優先 data/failure_history.csv（欄位 recency_days, alarms_90d, pressure, failed），
     找不到或不合格就改用「示範合成資料」（固定亂數種子，可重現，且不代表任何真實設備）。
  2. Z-Score 標準化 + 批次梯度下降訓練邏輯迴歸（模型只訓練一次並快取）。
  3. 輸入檢核（物理範圍 / 外插）、機率預測、門檻掃描。
"""
import csv
import math
import os
import random
import statistics
from functools import lru_cache

try:
    from . import skill_common as sc
except ImportError:  # 以頂層模組方式匯入時
    import skill_common as sc

FEATURES = [
    {"key": "recency_days", "label": "距上次維修天數", "unit": "天"},
    {"key": "alarms_90d",   "label": "近 90 天警報次數", "unit": "次"},
    {"key": "pressure",     "label": "運轉壓力", "unit": "MPa"},
]
KEYS = [f["key"] for f in FEATURES]
LABELS = {f["key"]: f["label"] for f in FEATURES}
UNITS = {f["key"]: f["unit"] for f in FEATURES}
DEFAULTS = {"recency_days": 45, "alarms_90d": 12, "pressure": 1.8}

PHYSICAL_LIMITS = {"recency_days": (0, 3650), "alarms_90d": (0, 500), "pressure": (0, 50)}
Z_BLOCK = 6.0          # |z| 超過此值：嚴重偏離訓練資料，拒絕預測
SEED = 20261106
VAL_RATIO = 0.30       # 驗證集比例（用於評估與門檻掃描）
MIN_ROWS = 50
SYNTHETIC_SOURCE = "synthetic_failure_demo_v1"
CSV_SOURCE = "data/failure_history.csv"


# ---------------------------------------------------------------- 基本數學
def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def parse_values(raw=None, **kwargs):
    """把 dict / list / 關鍵字參數整理成 {key: float}；回傳 (values, errors)。缺值以 DEFAULTS 補。"""
    merged = dict(DEFAULTS)
    if isinstance(raw, dict):
        merged.update({k: v for k, v in raw.items() if k in KEYS and v is not None})
    elif isinstance(raw, (list, tuple)):
        merged.update({k: v for k, v in zip(KEYS, raw) if v is not None})
    merged.update({k: v for k, v in kwargs.items() if k in KEYS and v is not None})

    values, errors = {}, []
    for k in KEYS:
        try:
            v = float(merged[k])
            if not math.isfinite(v):
                raise ValueError
            values[k] = v
        except (TypeError, ValueError):
            errors.append(f"{LABELS[k]}（{k}）必須為有限數值，收到：{merged[k]!r}")
    return values, errors


# ---------------------------------------------------------------- 資料
def _synthetic_rows(n: int = 600):
    """示範合成資料：故障標籤由已知的 logit 公式抽樣產生（約 2 成為故障，刻意不平衡）。"""
    rng = random.Random(SEED)
    rows = []
    for _ in range(n):
        recency = rng.betavariate(1.5, 3.0) * 120.0
        alarms = float(min(30, int(rng.expovariate(1.0 / 6.0))))
        pressure = min(3.0, max(0.5, rng.gauss(1.5, 0.4)))
        logit = -6.5 + 0.04 * recency + 0.25 * alarms + 1.1 * pressure
        failed = 1 if rng.random() < sigmoid(logit) else 0
        rows.append(([recency, alarms, pressure], failed))
    return rows


def _csv_rows(path: str):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in KEYS + ["failed"] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV 缺少欄位：{missing}")
        for r in reader:
            try:
                x = [float(r[k]) for k in KEYS]
                y = int(float(r["failed"]))
            except (TypeError, ValueError):
                continue
            if all(math.isfinite(v) for v in x) and y in (0, 1):
                rows.append((x, y))
    return rows


def load_dataset():
    """回傳 (rows, source, note)。"""
    path = os.path.join(sc.project_root(), "data", "failure_history.csv")
    note = ""
    if os.path.isfile(path):
        try:
            rows = _csv_rows(path)
            labels = {y for _, y in rows}
            if len(rows) >= MIN_ROWS and labels == {0, 1}:
                return rows, CSV_SOURCE, ""
            note = f"{CSV_SOURCE} 不合格（需 ≥{MIN_ROWS} 筆且同時含故障/未故障），已改用示範合成資料。"
        except (OSError, ValueError) as e:
            note = f"讀取 {CSV_SOURCE} 失敗（{e}），已改用示範合成資料。"
    return _synthetic_rows(), SYNTHETIC_SOURCE, note


# ---------------------------------------------------------------- 訓練
def train_logistic(Z, y, lr=0.5, epochs=600, l2=1e-3):
    n, d = len(Z), len(Z[0])
    w, b = [0.0] * d, 0.0
    for _ in range(epochs):
        gw, gb = [0.0] * d, 0.0
        for xi, yi in zip(Z, y):
            e = sigmoid(b + sum(wj * xj for wj, xj in zip(w, xi))) - yi
            gb += e
            for j in range(d):
                gw[j] += e * xi[j]
        for j in range(d):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return w, b


def log_loss(probs, labels) -> float:
    eps = 1e-12
    return -sum(
        yi * math.log(max(p, eps)) + (1 - yi) * math.log(max(1 - p, eps))
        for p, yi in zip(probs, labels)
    ) / len(labels)


def auc_score(probs, labels) -> float:
    pos = [p for p, y in zip(probs, labels) if y == 1]
    neg = [p for p, y in zip(probs, labels) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = sum((pp > pn) + 0.5 * (pp == pn) for pp in pos for pn in neg)
    return wins / (len(pos) * len(neg))


@lru_cache(maxsize=1)
def get_model() -> dict:
    rows, source, note = load_dataset()
    rng = random.Random(SEED)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    n_val = max(10, int(round(len(rows) * VAL_RATIO)))
    val_idx, tr_idx = idx[:n_val], idx[n_val:]

    X_tr = [rows[i][0] for i in tr_idx]
    y_tr = [rows[i][1] for i in tr_idx]
    X_va = [rows[i][0] for i in val_idx]
    y_va = [rows[i][1] for i in val_idx]

    cols = list(zip(*X_tr))
    means = [statistics.fmean(c) for c in cols]
    stds = [statistics.pstdev(c) or 1.0 for c in cols]
    mins, maxs = [min(c) for c in cols], [max(c) for c in cols]

    def zrow(x):
        return [(v - m) / s for v, m, s in zip(x, means, stds)]

    Z_tr = [zrow(x) for x in X_tr]
    w_z, b_z = train_logistic(Z_tr, y_tr)

    def prob_of(x):
        z = zrow(x)
        return sigmoid(b_z + sum(wj * zj for wj, zj in zip(w_z, z)))

    tr_probs = [prob_of(x) for x in X_tr]
    va_probs = [prob_of(x) for x in X_va]
    acc = sum((p >= 0.5) == bool(y) for p, y in zip(va_probs, y_va)) / len(y_va)

    w_raw = [wj / s for wj, s in zip(w_z, stds)]
    b_raw = b_z - sum(wj * m / s for wj, m, s in zip(w_z, means, stds))

    return {
        "data_source": source, "load_note": note,
        "means": dict(zip(KEYS, means)), "stds": dict(zip(KEYS, stds)),
        "mins": dict(zip(KEYS, mins)), "maxs": dict(zip(KEYS, maxs)),
        "w_z": dict(zip(KEYS, w_z)), "b_z": b_z,
        "w_raw": dict(zip(KEYS, w_raw)), "b_raw": b_raw,
        "val_probs": va_probs, "val_labels": y_va,
        "metrics": {
            "n_train": len(tr_idx), "n_val": len(val_idx),
            "pos_rate_train": round(sum(y_tr) / len(y_tr), 4),
            "pos_rate_val": round(sum(y_va) / len(y_va), 4),
            "accuracy_at_0_5": round(acc, 4),
            "auc": round(auc_score(va_probs, y_va), 4),
            "log_loss_train": round(log_loss(tr_probs, y_tr), 4),
            "log_loss_val": round(log_loss(va_probs, y_va), 4),
        },
        "epochs": 600, "learning_rate": 0.5, "l2": 1e-3,
    }


# ---------------------------------------------------------------- 檢核與預測
def check_inputs(values: dict, model: dict) -> dict:
    """物理範圍（硬性）、嚴重外插（硬性）、超出訓練範圍（警告）。"""
    violations, warnings, z_scores = [], [], {}
    for k in KEYS:
        x = values[k]
        lo, hi = PHYSICAL_LIMITS[k]
        z = (x - model["means"][k]) / model["stds"][k]
        z_scores[k] = z
        if not (lo <= x <= hi):
            violations.append(f"{LABELS[k]} = {x:g} {UNITS[k]} 超出物理合理範圍 [{lo}, {hi}]")
        elif abs(z) > Z_BLOCK:
            violations.append(f"{LABELS[k]} = {x:g} {UNITS[k]} 嚴重偏離訓練資料（|z| = {abs(z):.1f} > {Z_BLOCK:g}），模型外插不可信")
        elif x < model["mins"][k] or x > model["maxs"][k]:
            warnings.append(f"{LABELS[k]} = {x:g} {UNITS[k]} 超出訓練資料範圍 [{model['mins'][k]:.1f}, {model['maxs'][k]:.1f}]，屬外插，結果僅供參考")
    return {"violations": violations, "warnings": warnings, "z_scores": z_scores}


def predict_logit(model: dict, values: dict) -> float:
    return model["b_raw"] + sum(model["w_raw"][k] * values[k] for k in KEYS)


def scan_thresholds(probs, labels, c_down: float, c_insp: float, step: float = 0.01):
    """掃描門檻 θ：機率 ≥ θ 視為預警。Cost(θ) = C_down·FN + C_inspect·FP。"""
    out = []
    n_steps = int(round(1.0 / step))
    for i in range(n_steps + 1):
        th = round(i * step, 4)
        tp = fp = fn = tn = 0
        for p, y in zip(probs, labels):
            alert = p >= th
            if alert and y:
                tp += 1
            elif alert and not y:
                fp += 1
            elif (not alert) and y:
                fn += 1
            else:
                tn += 1
        out.append({"threshold": th, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                    "total_cost": round(c_down * fn + c_insp * fp, 2)})
    return out


def best_threshold(curve):
    """取最低成本；若多個門檻同分，取其中位數（避免偏向掃描區間端點）。"""
    cmin = min(r["total_cost"] for r in curve)
    tied = [r for r in curve if r["total_cost"] == cmin]
    return tied[len(tied) // 2], len(tied)
