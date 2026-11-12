"""
_steel_model.py - page11 鋼板表面缺陷分類的共用資料與模型（skill_17 / 18 / 19 共用）

特徵：area 缺陷面積 (mm²)、aspect_ratio 長寬比（長邊/短邊，≥1）、contrast 灰階對比度 (0–255)
類別：Scratch 劃痕、Crack 裂紋、Inclusion 夾雜、Scale 氧化皮（示範資料）

資料來源（依序）：
  1. data/steel_defects.csv  欄位 area,aspect_ratio,contrast,defect_class（類別名稱任意字串）
  2. 不存在時使用固定 seed 的「示範資料」：四類缺陷各自依我設定的高斯分佈合成並刻意讓類別有重疊。
     這是示範用的假想分佈，不是真實鋼板缺陷資料。

資料切分（分層、固定 seed）：訓練 60% / 驗證 20% / 測試 20%
  * 訓練集：長出完整 CART（刻意不限制太嚴，讓剪枝有東西可剪）
  * 驗證集：只用來挑選剪枝係數 α
  * 測試集：只用來報告剪枝前後的最終準確率與混淆矩陣，從不用來做任何選擇
  （規格寫「以測試集選 α」；我多切一份驗證集，因為用測試集選 α 再報告同一份測試集準確率會偏樂觀。）
"""

import csv
import hashlib
import math
import os
import random

try:
    from ._common import default_output_path
    from . import _cart as cart
except ImportError:
    from _common import default_output_path
    import _cart as cart

MODEL_ID = "CART_DEFECT_V1"
FEATURES = ["area", "aspect_ratio", "contrast"]
LABELS = {"area": "缺陷面積", "aspect_ratio": "長寬比", "contrast": "灰階對比度"}
UNITS = {"area": "mm²", "aspect_ratio": "", "contrast": ""}
HARD_LIMITS = {"area": (0.0, 10000.0), "aspect_ratio": (1.0, 100.0), "contrast": (0.0, 255.0)}
CLASS_LABELS = {"Scratch": "劃痕", "Crack": "裂紋", "Inclusion": "夾雜", "Scale": "氧化皮"}
SPLIT = (0.6, 0.2, 0.2)
SPLIT_SEED = 17
MIN_TEST_ACC = 0.70
MIN_MARGIN = 0.10          # 測試集準確率需勝過「永遠猜最多類」至少 10 個百分點
MIN_CLASS_TRAIN = 5
_CACHE = {}

# 示範類別分佈：(面積 μ,σ)、(長寬比 μ,σ)、(對比度 μ,σ)
_DEMO_CLASSES = {
    "Scratch":   ((145, 45), (4.2, 1.0), (88, 18)),
    "Crack":     ((80, 30), (6.0, 1.5), (132, 22)),
    "Inclusion": ((52, 20), (1.5, 0.5), (152, 22)),
    "Scale":     ((245, 65), (2.0, 0.65), (68, 18)),
}
DEMO_EXAMPLES = {   # 頁面「快速範例」使用：各類別分佈中心
    "Scratch": [145, 4.2, 88], "Crack": [80, 6.0, 132], "Inclusion": [52, 1.5, 152], "Scale": [245, 2.0, 68],
}


def clean_num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def generate_demo(per_class: int = 150, seed: int = 31):
    rng = random.Random(seed)
    rows = []
    for name, (a, r, c) in _DEMO_CLASSES.items():
        for _ in range(per_class):
            rows.append({"area": round(max(5.0, rng.gauss(*a)), 1), "aspect_ratio": round(max(1.0, rng.gauss(*r)), 2),
                         "contrast": round(min(255.0, max(0.0, rng.gauss(*c))), 1), "defect_class": name})
    return rows


def load_data():
    path = default_output_path("steel_defects.csv")
    if os.path.exists(path):
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                need = FEATURES + ["defect_class"]
                if not reader.fieldnames or not set(need) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {need}")
                for rec in reader:
                    row = {k: float(rec[k]) for k in FEATURES}
                    if not all(math.isfinite(row[k]) for k in FEATURES):
                        raise ValueError("特徵必須是有限數值")
                    row["defect_class"] = rec["defect_class"].strip()
                    if not row["defect_class"]:
                        raise ValueError("defect_class 不可為空")
                    rows.append(row)
            if len(rows) < 80 or len({r["defect_class"] for r in rows}) < 2:
                raise ValueError("至少需要 80 筆資料與 2 個類別")
            return rows, "data/steel_defects.csv"
        except Exception as e:
            print(f"讀取 steel_defects.csv 失敗：{e}，改用示範資料", flush=True)
    return generate_demo(), "synthetic_demo (seed=31，示範分佈非真實鋼板資料)"


def validate_inputs(area, aspect_ratio, contrast):
    """回傳 (向量 or None, 錯誤清單)。"""
    errors, vec = [], []
    for f, v in zip(FEATURES, (area, aspect_ratio, contrast)):
        lo, hi = HARD_LIMITS[f]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{LABELS[f]} 必須為數值")
        elif not math.isfinite(v):
            errors.append(f"{LABELS[f]} 不可為 NaN 或無限大")
        elif (f == "area" and v <= 0) or not lo <= v <= hi:
            errors.append(f"{LABELS[f]} = {v:g} 超出合理範圍 ({'>' if f == 'area' else '['}{lo:g}, {hi:g}]")
        else:
            vec.append(float(v))
    return (vec if not errors else None), errors


def get_model() -> dict:
    rows, source = load_data()
    sig = hashlib.sha1((source + str(len(rows)) + "".join(f"{r['area']}{r['aspect_ratio']}{r['contrast']}{r['defect_class']}"
                                                          for r in rows[::7])).encode()).hexdigest()[:12]
    if sig in _CACHE:
        return _CACHE[sig]
    classes = sorted({r["defect_class"] for r in rows}, key=lambda c: (list(CLASS_LABELS).index(c) if c in CLASS_LABELS else 99, c))
    cidx = {c: i for i, c in enumerate(classes)}
    by_class = {c: [] for c in classes}
    for i, r in enumerate(rows):
        by_class[r["defect_class"]].append(i)
    rng = random.Random(SPLIT_SEED)
    tr, va, te = [], [], []
    for c in classes:
        idx = by_class[c][:]
        rng.shuffle(idx)
        n = len(idx)
        n_tr, n_va = int(n * SPLIT[0]), int(n * SPLIT[1])
        tr += idx[:n_tr]; va += idx[n_tr:n_tr + n_va]; te += idx[n_tr + n_va:]

    def pack(ids):
        return [[rows[i][f] for f in FEATURES] for i in ids], [cidx[rows[i]["defect_class"]] for i in ids]

    Xtr, ytr = pack(tr); Xva, yva = pack(va); Xte, yte = pack(te)
    stats = {}
    for j, f in enumerate(FEATURES):
        col = [r[j] for r in Xtr]
        m = sum(col) / len(col)
        sd = math.sqrt(sum((v - m) ** 2 for v in col) / (len(col) - 1))
        stats[f] = {"mean": m, "std": sd if sd > 0 else 1e-9, "min": min(col), "max": max(col)}
    tree = cart.fit_cart(Xtr, ytr, len(classes))
    seq = cart.prune_sequence(tree, len(Xtr))
    for item in seq:
        item["train_acc"] = cart.accuracy(item["tree"], Xtr, ytr)
        item["val_acc"] = cart.accuracy(item["tree"], Xva, yva)
    counts = [ytr.count(i) for i in range(len(classes))]
    model = {
        "source": source, "classes": classes, "class_labels": [CLASS_LABELS.get(c, c) for c in classes],
        "Xtr": Xtr, "ytr": ytr, "Xva": Xva, "yva": yva, "Xte": Xte, "yte": yte, "stats": stats,
        "tree": tree, "seq": seq, "train_counts": counts,
        "n_total": len(rows), "majority_baseline_test": max(yte.count(i) for i in range(len(classes))) / len(yte),
    }
    _CACHE[sig] = model
    return model


def model_problems(model: dict, tree=None) -> list:
    """模型品質 Guardrail：回傳阻擋原因。"""
    tree = tree or model["tree"]
    out = []
    small = [model["classes"][i] for i, n in enumerate(model["train_counts"]) if n < MIN_CLASS_TRAIN]
    if small:
        out.append(f"類別 {'、'.join(small)} 的訓練樣本少於 {MIN_CLASS_TRAIN} 筆，無法可靠學習")
    acc = cart.accuracy(tree, model["Xte"], model["yte"])
    base = model["majority_baseline_test"]
    if acc < MIN_TEST_ACC:
        out.append(f"測試集準確率 {acc * 100:.1f}% < {MIN_TEST_ACC * 100:.0f}%，模型不可靠")
    elif acc < base + MIN_MARGIN:
        out.append(f"測試集準確率 {acc * 100:.1f}% 未明顯優於「永遠猜最多類」的 {base * 100:.1f}%（需高出 {MIN_MARGIN * 100:.0f} 個百分點）")
    return out
