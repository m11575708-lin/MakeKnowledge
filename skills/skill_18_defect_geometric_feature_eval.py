"""
skill_18_defect_geometric_feature_eval.py - 缺陷幾何與光學特徵影響力評估技能

對應系統規格：US-10 / 11. 鋼板表面缺陷分類與特徵評估頁
演算法機制：模型檢核 -> 逐節點吉尼下降量 -> 歸一化為特徵影響力
            -> 測試集排列重要度交叉檢查 -> Guardrail

特徵影響力 = 該特徵在樹中所有切分節點的 (n_t/N)·ΔGini 加總，再歸一化為總和 1（與 skill_15 的 MDI 同一概念，作用在單棵 CART）。
限制：這是「模型怎麼用特徵」，不代表物理因果；單棵樹的重要度對訓練資料很敏感，也偏向可切分次數多的連續特徵，
所以另外用測試集排列重要度（打亂單一特徵後準確率下降多少，重複 5 次平均）做交叉檢查。
"""

import json
import random

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _cart as cart
    from ._steel_model import FEATURES, LABELS, MODEL_ID, get_model, model_problems
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _cart as cart
    from _steel_model import FEATURES, LABELS, MODEL_ID, get_model, model_problems

SKILL_NAME = "skill_18_defect_geometric_feature_eval"
PERM_REPEATS, PERM_GAP, DOMINANCE_WARN = 5, 0.05, 0.80

PLAN = [
    ("模型編號與前置檢核", "Boundary & Type Validation", "math"),
    ("逐節點計算吉尼下降量", "Gini Impurity Decrease per Split  ΔI = I(t) - Σ(n_c/n_t)·I(c)", "Python Built-in"),
    ("歸一化為特徵影響力", "Gini-based Feature Importance (normalized)", "Python Built-in"),
    ("測試集排列重要度交叉檢查", "Permutation Importance Cross-check", "random"),
    ("模型品質與影響力分布 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def evaluate_defect_features(model_id: str = MODEL_ID, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("defect_feature_eval_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "model_id": model_id, "feature_importance": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    if not isinstance(model_id, str) or model_id.strip() != MODEL_ID:
        msg = f"找不到模型 {model_id!r}（目前只有 {MODEL_ID}）"
        log.add("輸入驗證失敗：" + msg)
        return blocked("模型編號無效", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + msg, [msg])
    model = get_model()
    tree = model["tree"]
    log.add(f"模型 {MODEL_ID} 存在（資料：{model['source']}；完整樹 {cart.n_leaves(tree)} 個葉節點、{cart.n_splits(tree)} 次切分、訓練 {len(model['Xtr'])} 筆）。")

    # 2
    raw = cart.gini_importance(tree, len(FEATURES))
    splits_by_f = [0] * len(FEATURES)
    def walk(nd):
        if not cart.is_leaf(nd):
            splits_by_f[nd["feature"]] += 1
            walk(nd["left"]); walk(nd["right"])
    walk(tree)
    log.add("走訪每個切分節點，計算 ΔGini = n_t·I(t) - n_l·I(l) - n_r·I(r)，除以訓練總數 N 後累加到該節點使用的特徵：" + "；".join(
        f"{LABELS[f]} 用於 {splits_by_f[i]} 次切分、累計 {raw[i]:.4f}" for i, f in enumerate(FEATURES)) + f"（根節點吉尼 {tree['impurity']:.3f}）。")

    # 3
    total = sum(raw)
    if total <= 0:
        log.add("樹沒有任何有效切分（總下降量為 0），無法計算影響力。")
        return blocked("樹沒有切分", "BLOCKED_BY_GUARDRAIL (no splits)", "決策樹沒有任何切分，無法評估特徵影響力")
    imp = [v / total for v in raw]
    order = sorted(range(len(FEATURES)), key=lambda j: -imp[j])
    log.add("歸一化（÷ 總下降量 " + f"{total:.4f}）：" + "、".join(f"{LABELS[FEATURES[j]]} {imp[j]:.3f}" for j in order) + f"（總和 {sum(imp):.3f}）。")

    # 4
    rng = random.Random(99)
    Xte, yte = model["Xte"], model["yte"]
    base = cart.accuracy(tree, Xte, yte)
    perm = []
    for f in range(len(FEATURES)):
        drops = []
        for _ in range(PERM_REPEATS):
            col = [r[f] for r in Xte]
            rng.shuffle(col)
            Xp = [r[:f] + [col[i]] + r[f + 1:] for i, r in enumerate(Xte)]
            drops.append(base - cart.accuracy(tree, Xp, yte))
        perm.append(sum(drops) / PERM_REPEATS)
    perm_top = max(range(len(FEATURES)), key=lambda j: perm[j])
    log.add(f"測試集基準準確率 {base * 100:.1f}%；逐一打亂單一特徵（各 {PERM_REPEATS} 次平均）後準確率下降："
            + "、".join(f"{LABELS[f]} {v * 100:+.1f} 個百分點" for f, v in zip(FEATURES, perm)) + f"；排列法最重要者為「{LABELS[FEATURES[perm_top]]}」。")

    # 5
    problems = model_problems(model)
    if problems:
        return blocked("Guardrail 已攔截，不輸出影響力", "BLOCKED_BY_GUARDRAIL (model quality)",
                       "為避免誤導，已拒絕輸出特徵影響力（模型本身不可靠）：" + "；".join(problems), problems)
    warnings = []
    top = order[0]
    if perm_top != top and perm[perm_top] - perm[top] > PERM_GAP:
        warnings.append(f"吉尼影響力最高的是「{LABELS[FEATURES[top]]}」，但排列重要度最高的是「{LABELS[FEATURES[perm_top]]}」，兩種方法明顯不一致，請謹慎解讀")
    if imp[top] > DOMINANCE_WARN:
        warnings.append(f"「{LABELS[FEATURES[top]]}」獨占 {imp[top] * 100:.0f}% 的影響力，模型幾乎只靠單一特徵分類")
    warnings.append("特徵影響力描述模型如何使用特徵，不代表物理因果")
    real = [w for w in warnings if not w.startswith("特徵影響力描述")]
    guardrail = "PASSED" if not real else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（模型品質通過、影響力總和為 1）。" + ("；".join(real) if real else ""))

    ranking = [{"rank": r + 1, "feature": FEATURES[j], "label": LABELS[FEATURES[j]], "importance": round(imp[j], 4),
                "splits_used": splits_by_f[j], "permutation_importance": round(perm[j], 4)} for r, j in enumerate(order)]
    return finish({
        "status": "success", "found": True, "model_id": MODEL_ID,
        "feature_importance": {FEATURES[j]: round(imp[j], 4) for j in range(len(FEATURES))},
        "ranking": ranking, "top_feature": FEATURES[top], "top_feature_label": LABELS[FEATURES[top]],
        "data_source": model["source"], "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"影響力最高的是「{LABELS[FEATURES[top]]}」（{imp[top] * 100:.0f}%），其次為「{LABELS[FEATURES[order[1]]]}」（{imp[order[1]] * 100:.0f}%）。",
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_18_defect_geometric_feature_eval ===")
    print(json.dumps(evaluate_defect_features(), ensure_ascii=False, indent=2))
