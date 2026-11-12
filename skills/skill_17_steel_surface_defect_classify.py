"""
skill_17_steel_surface_defect_classify.py - 鋼板表面缺陷 CART 決策樹多類別分類技能

對應系統規格：US-10 / 11. 鋼板表面缺陷分類與特徵評估頁
演算法機制：輸入防呆 -> 載入資料與分層切分 -> CART 吉尼切分遞迴建樹
            -> 沿決策路徑分類並彙整測試集混淆矩陣 -> Guardrail

說明：
  * 本技能使用「完整（未剪枝）」的 CART；剪枝由 skill_19 負責。
  * 預測類別 = 落入葉節點的多數類；class_probabilities 是該葉節點內各類別的訓練樣本比例（不是校準過的機率）。
  * confusion_matrix 以測試集計算，列＝真實類別、欄＝預測類別；訓練集準確率另列，兩者差距大代表過度擬合。
  * 沒有 data/steel_defects.csv 時使用固定 seed 的示範資料（synthetic_demo），不是真實鋼板缺陷資料。
"""

import json

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _cart as cart
    from ._steel_model import FEATURES, LABELS, UNITS, clean_num, get_model, model_problems, validate_inputs, \
        MIN_TEST_ACC, MIN_MARGIN, SPLIT
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _cart as cart
    from _steel_model import FEATURES, LABELS, UNITS, clean_num, get_model, model_problems, validate_inputs, \
        MIN_TEST_ACC, MIN_MARGIN, SPLIT

SKILL_NAME = "skill_17_steel_surface_defect_classify"
BLOCK_Z, WARN_Z = 4.0, 3.0
SMALL_LEAF, LOW_PURITY, OVERFIT_GAP = 5, 0.60, 0.10
NEAR_SPLIT_Z = 0.05      # 與某個切分門檻的距離小於 0.05 個標準差，視為貼近邊界

PLAN = [
    ("缺陷特徵輸入防呆", "Boundary & Type Validation", "math"),
    ("載入缺陷資料與分層切分", "Stratified Train/Validation/Test Split (60/20/20)", "csv, random"),
    ("CART 吉尼切分遞迴建樹", "CART Decision Tree (Gini Impurity Split)", "Python Built-in"),
    ("沿決策路徑分類並彙整混淆矩陣", "Tree Traversal Classification & Confusion Matrix", "Python Built-in"),
    ("模型品質與外插 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def classify_steel_defect(area=150, aspect_ratio=4.2, contrast=85, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("steel_defect_classify_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    echo = [clean_num(v) for v in (area, aspect_ratio, contrast)]

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "features": echo, "defect_class": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    vec, errors = validate_inputs(area, aspect_ratio, contrast)
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    echo = vec
    log.add("特徵：" + "、".join(f"{LABELS[f]} {v:g}{UNITS[f]}" for f, v in zip(FEATURES, vec))
            + "，皆為合理範圍內的有限數值（面積 >0、長寬比 ≥1、對比度 0–255）。")

    # 2
    model = get_model()
    k = len(model["classes"])
    log.add(f"資料來源：{model['source']}；共 {model['n_total']} 筆、{k} 類（{'、'.join(model['classes'])}）。依類別分層切分："
            f"訓練 {len(model['Xtr'])}、驗證 {len(model['Xva'])}、測試 {len(model['Xte'])} 筆（{SPLIT[0]:.0%}/{SPLIT[1]:.0%}/{SPLIT[2]:.0%}，固定 seed）；"
            "測試集不參與任何選擇。")

    # 3
    tree = model["tree"]
    tr_acc = cart.accuracy(tree, model["Xtr"], model["ytr"])
    te_acc = cart.accuracy(tree, model["Xte"], model["yte"])
    log.add(f"以吉尼不純度 I_G = 1 - Σp² 遞迴切分：每個節點掃描全部 {len(FEATURES)} 個特徵的所有相鄰值中點，選吉尼下降最大者"
            f"（最大深度 10、葉節點至少 2 筆）。長出完整樹：{cart.n_leaves(tree)} 個葉節點、深度 {cart.depth(tree)}、{cart.n_splits(tree)} 次切分；"
            f"訓練準確率 {tr_acc * 100:.1f}%、測試準確率 {te_acc * 100:.1f}%。")

    # 4
    leaf = cart.find_leaf(tree, vec)
    pred = cart.majority(leaf)
    path = cart.decision_path(tree, vec, FEATURES)
    probs = {c: round(leaf["counts"][i] / leaf["n"], 4) for i, c in enumerate(model["classes"])}
    cm = cart.confusion_matrix(tree, model["Xte"], model["yte"], k)
    recall = [cm[i][i] / sum(cm[i]) if sum(cm[i]) else None for i in range(k)]
    log.add("決策路徑：" + (" → ".join(f"{LABELS[p['feature']]} {p['value']:g} {'≤' if p['op'] == '<=' else '>'} {p['threshold']:.2f}" for p in path) or "（根節點即葉節點）")
            + f"；落入葉節點（{leaf['n']} 筆訓練樣本：" + "、".join(f"{c} {n}" for c, n in zip(model["classes"], leaf["counts"]) if n)
            + f"），多數類 → {model['classes'][pred]}（{model['class_labels'][pred]}）。測試集混淆矩陣（列＝真實、欄＝預測）對角線共 {sum(cm[i][i] for i in range(k))}/{len(model['yte'])} 筆正確。")

    # 5
    problems = model_problems(model)
    warnings = []
    for f, v in zip(FEATURES, vec):
        st = model["stats"][f]
        z = (v - st["mean"]) / st["std"]
        desc = f"{LABELS[f]}={v:g}{UNITS[f]}"
        if abs(z) > BLOCK_Z:
            problems.append(f"{desc} 的 |z|={abs(z):.2f} > {BLOCK_Z:g}，遠離訓練資料範圍")
        elif v < st["min"] or v > st["max"]:
            warnings.append(f"{desc} 超出訓練資料範圍 [{st['min']:.1f}, {st['max']:.1f}]，決策樹在範圍外只會沿用邊緣葉節點，屬外插")
        elif abs(z) > WARN_Z:
            warnings.append(f"{desc} 的 |z|={abs(z):.2f} > {WARN_Z:g}")
    if problems:
        kind = "extrapolation" if any("|z|" in p for p in problems) else "model quality"
        return blocked("Guardrail 已攔截，不輸出分類", f"BLOCKED_BY_GUARDRAIL ({kind})",
                       "為避免誤導，已拒絕輸出缺陷分類：" + "；".join(problems), problems + warnings)
    purity = leaf["counts"][pred] / leaf["n"]
    if leaf["n"] < SMALL_LEAF:
        warnings.append(f"落入的葉節點只有 {leaf['n']} 筆訓練樣本（< {SMALL_LEAF}），判定不穩定，可能是過度擬合的結果")
    if purity < LOW_PURITY:
        warnings.append(f"葉節點純度僅 {purity * 100:.0f}%，這類特徵組合在訓練資料中本來就容易混淆")
    for p in path:
        dist = abs(p["value"] - p["threshold"]) / model["stats"][p["feature"]]["std"]
        if dist < NEAR_SPLIT_Z:
            warnings.append(f"{LABELS[p['feature']]} {p['value']:g} 非常接近切分門檻 {p['threshold']:.2f}，量測稍有誤差分類就可能改變")
            break
    if tr_acc - te_acc > OVERFIT_GAP:
        warnings.append(f"完整樹訓練準確率 {tr_acc * 100:.1f}% 比測試集 {te_acc * 100:.1f}% 高出 {(tr_acc - te_acc) * 100:.1f} 個百分點，有過度擬合跡象，建議參考 skill_19 剪枝後的結果")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（測試集準確率 {te_acc * 100:.1f}% ≥ {MIN_TEST_ACC * 100:.0f}% 且高於多數類基準 {model['majority_baseline_test'] * 100:.1f}% 達 {MIN_MARGIN * 100:.0f} 個百分點、輸入未嚴重外插）。"
            + ("；".join(warnings) if warnings else ""))

    return finish({
        "status": "success", "found": True, "features": vec, "feature_names": FEATURES,
        "defect_class": model["classes"][pred], "defect_class_label": model["class_labels"][pred],
        "class_probabilities": probs, "leaf_samples": leaf["n"], "leaf_purity": round(purity, 4),
        "decision_path": [{"feature": p["feature"], "label": LABELS[p["feature"]], "op": p["op"],
                           "threshold": round(p["threshold"], 3), "value": p["value"]} for p in path],
        "class_names": model["classes"], "class_labels": model["class_labels"],
        "confusion_matrix": cm, "per_class_recall": [None if r is None else round(r, 4) for r in recall],
        "accuracy_train": round(tr_acc, 4), "accuracy_test": round(te_acc, 4),
        "majority_baseline": round(model["majority_baseline_test"], 4),
        "n_leaves": cart.n_leaves(tree), "tree_depth": cart.depth(tree), "n_test": len(model["yte"]),
        "data_source": model["source"], "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"判定為「{model['classes'][pred]}（{model['class_labels'][pred]}）」，所在葉節點純度 {purity * 100:.0f}%；完整樹測試集準確率 {te_acc * 100:.1f}%。",
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_17_steel_surface_defect_classify ===")
    print(json.dumps(classify_steel_defect(150, 4.2, 85), ensure_ascii=False, indent=2))
