"""
_quality_model.py - page10 三個 Skill 共用的隨機森林訓練與快取

資料切分：80% 訓練（森林內部再做 Bootstrap + OOB）、20% 測試（固定 seed）。
同一組 (樹數, 資料簽章) 在同一個行程內只訓練一次。
"""

import hashlib
import math
import random

try:
    from ._forest import RandomForest
    from ._quality_data import FEATURES, load_samples
except ImportError:
    from _forest import RandomForest
    from _quality_data import FEATURES, load_samples

TREES_MIN, TREES_MAX = 10, 300
TEST_RATIO = 0.20
SPLIT_SEED = 3
FOREST_SEED = 7
MIN_HOLDOUT_ACC = 0.70
MIN_OOB_ACC = 0.70
_CACHE = {}


def validate_n_trees(n_trees):
    if isinstance(n_trees, bool) or not isinstance(n_trees, (int, float)) or not math.isfinite(n_trees) \
            or int(n_trees) != n_trees:
        return None, "樹數量必須為整數"
    n = int(n_trees)
    if not TREES_MIN <= n <= TREES_MAX:
        return None, f"樹數量 {n} 超出允許範圍 [{TREES_MIN}, {TREES_MAX}]"
    return n, None


def get_model(n_trees: int = 100) -> dict:
    rows, source = load_samples()
    sig = hashlib.sha1((source + str(len(rows)) + str(sum(r["defect"] for r in rows))
                        + str(round(sum(r["temp"] for r in rows), 3))).encode()).hexdigest()[:12]
    key = (n_trees, sig)
    if key in _CACHE:
        return _CACHE[key]
    X = [[r[f] for f in FEATURES] for r in rows]
    y = [r["defect"] for r in rows]
    idx = list(range(len(rows)))
    random.Random(SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * TEST_RATIO))
    te, tr = idx[:n_test], idx[n_test:]
    Xtr, ytr = [X[i] for i in tr], [y[i] for i in tr]
    Xte, yte = [X[i] for i in te], [y[i] for i in te]
    forest = RandomForest(n_trees=n_trees, seed=FOREST_SEED).fit(Xtr, ytr)
    stats = {}
    for j, f in enumerate(FEATURES):
        col = [r[j] for r in Xtr]
        m = sum(col) / len(col)
        sd = math.sqrt(sum((v - m) ** 2 for v in col) / (len(col) - 1))
        good = [r[j] for r, t in zip(Xtr, ytr) if t == 0]
        gm = sum(good) / len(good) if good else m
        stats[f] = {"mean": m, "std": sd if sd > 0 else 1e-9, "min": min(col), "max": max(col), "good_mean": gm}
    tp = sum(1 for xi, yi in zip(Xte, yte) if yi == 1 and forest.predict(xi) == 1)
    fn = sum(1 for xi, yi in zip(Xte, yte) if yi == 1 and forest.predict(xi) == 0)
    fp = sum(1 for xi, yi in zip(Xte, yte) if yi == 0 and forest.predict(xi) == 1)
    model = {
        "forest": forest, "source": source, "stats": stats, "n_train": len(Xtr), "n_test": len(Xte),
        "holdout_accuracy": forest.accuracy(Xte, yte), "oob_accuracy": forest.oob_accuracy,
        "defect_rate": sum(y) / len(y), "recall": tp / (tp + fn) if tp + fn else None,
        "precision": tp / (tp + fp) if tp + fp else None, "Xte": Xte, "yte": yte,
    }
    _CACHE[key] = model
    return model


def quality_problems(model: dict) -> list:
    """模型品質 Guardrail：回傳阻擋原因清單。"""
    out = []
    if model["holdout_accuracy"] < MIN_HOLDOUT_ACC:
        out.append(f"測試集準確率 {model['holdout_accuracy'] * 100:.1f}% < {MIN_HOLDOUT_ACC * 100:.0f}%，模型不可靠")
    if model["oob_accuracy"] is None or model["oob_accuracy"] < MIN_OOB_ACC:
        o = model["oob_accuracy"]
        out.append(f"OOB 準確率 {'無法計算' if o is None else f'{o * 100:.1f}%'}，低於 {MIN_OOB_ACC * 100:.0f}%")
    return out


def resolve_batch(batch_id, batch_params):
    """決定要分析的參數。回傳 (params or None, batch_dict or None, errors, batches)。
    batch_params 優先；只給 batch_id 時由批次表取得；兩者都沒有時用規格範例參數。"""
    import re
    try:
        from ._quality_data import BATCH_ID_PATTERN, DEFAULT_PARAMS, load_batches, validate_params
    except ImportError:
        from _quality_data import BATCH_ID_PATTERN, DEFAULT_PARAMS, load_batches, validate_params
    batches, _ = load_batches()
    errors, batch = [], None
    if batch_id is not None:
        if not isinstance(batch_id, str) or not re.match(BATCH_ID_PATTERN, batch_id.strip()):
            errors.append("batch_id 格式需為 B-YYYY-NN，例如 B-2026-10")
        else:
            batch = next((b for b in batches if b["batch_id"] == batch_id.strip()), None)
            if batch is None:
                errors.append(f"找不到批次 {batch_id.strip()}（可用：{', '.join(b['batch_id'] for b in batches)}）")
    if errors:
        return None, None, errors, batches
    raw = batch_params if batch_params is not None else (batch["params"] if batch else DEFAULT_PARAMS)
    params, perr = validate_params(raw)
    return params, batch, perr, batches
