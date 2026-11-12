"""
skill_15_feature_importance_ranking.py - 隨機森林特徵重要度（MDI）排序技能

對應系統規格：US-09 / 10. 品質異常根本原因分析頁
演算法機制：輸入防呆 -> 載入資料與森林 -> 累加各節點吉尼不純度下降量
            -> 跨樹平均並歸一化排序 -> Guardrail（模型品質、與排列重要度交叉檢查）

MDI（Mean Decrease Impurity）：每個切分節點貢獻 (n_t/N)·ΔGini，同一特徵加總；單棵樹內歸一化後再對所有樹平均。
已知限制：MDI 偏向取值多的連續特徵，且是以訓練資料計算。因此另外在測試集算「排列重要度」
（打亂單一特徵後準確率下降多少）作交叉檢查，兩者最重要的特徵不一致時會警告。
重要度是「全域」的，描述模型整體依賴哪個參數，並不代表這個特徵「導致」了某一批的異常；單一批次的歸因由 skill_16 處理。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._quality_data import FEATURES, LABELS, UNITS
    from ._quality_model import get_model, quality_problems, resolve_batch, validate_n_trees, MIN_HOLDOUT_ACC
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _quality_data import FEATURES, LABELS, UNITS
    from _quality_model import get_model, quality_problems, resolve_batch, validate_n_trees, MIN_HOLDOUT_ACC

SKILL_NAME = "skill_15_feature_importance_ranking"
PERM_GAP = 0.05            # 排列法最高者領先 MDI 第一名的準確率下降量需超過此值才算「明顯不一致」
DOMINANCE_WARN = 0.60      # 單一特徵占比超過此值提醒
FLAT_WARN = 0.40           # 最大占比低於此值代表沒有明顯主因

PLAN = [
    ("批次與森林設定防呆", "Boundary & Type Validation", "math, re"),
    ("載入森林與各節點 Gini 下降量", "Gini Impurity Decrease per Split  ΔI = I(t) - Σ(n_c/n_t)·I(c)", "random"),
    ("跨樹平均並歸一化（MDI）", "Mean Decrease Impurity (MDI)", "Python Built-in"),
    ("排序並以排列重要度交叉檢查", "Feature Ranking & Permutation Importance Cross-check", "random"),
    ("模型品質與重要度分布 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def rank_feature_importance(batch_id=None, n_trees: int = 100, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("feature_importance_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "batch_id": batch_id, "feature_importance": [],
                       "top_feature": None, "warnings": warnings or [message], "guardrail_status": guardrail,
                       "answer_text": message})

    # 1
    n, n_err = validate_n_trees(n_trees)
    errors = [n_err] if n_err else []
    if batch_id is not None:
        _, _, berr, _ = resolve_batch(batch_id, None)
        errors += [e for e in berr if "batch_id" in e or "找不到批次" in e]
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    log.add(f"批次 {batch_id or '（未指定，使用全部歷史資料）'}；森林樹數量 N={n}。特徵重要度是以整份歷史資料訓練的森林計算，與批次參數無關，批次僅供標示。")

    # 2
    model = get_model(n)
    forest = model["forest"]
    n_splits = 0
    def _count(node):
        return 0 if node.feature is None else 1 + _count(node.left) + _count(node.right)
    n_splits = sum(_count(t.root) for t in forest.trees)
    log.add(f"載入 {n} 棵樹（資料：{model['source']}，訓練 {model['n_train']} 筆），共 {n_splits} 個切分節點（平均每棵 {n_splits / n:.1f} 個）。"
            "對每個切分節點計算 (n_t/N)·[I(t) - n_l/n_t·I(l) - n_r/n_t·I(r)]，其中 I = 1 - Σp²，並累加到該節點使用的特徵上。")

    # 3
    per_tree = [t.importance() for t in forest.trees]
    mdi = [sum(col) / len(col) for col in zip(*per_tree)]
    total = sum(mdi)
    mdi = [v / total for v in mdi] if total > 0 else mdi
    stds = []
    for j in range(len(FEATURES)):
        vals = [p[j] for p in per_tree]
        m = sum(vals) / len(vals)
        stds.append(math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)))
    log.add("各樹內先將特徵貢獻歸一化為總和 1，再對 " + f"{n} 棵樹取平均：" + "、".join(f"{LABELS[f]} {v:.3f}" for f, v in zip(FEATURES, mdi))
            + f"（總和 {sum(mdi):.3f}）；跨樹標準差 " + "、".join(f"{s:.3f}" for s in stds) + "。")

    # 4
    perm = forest.permutation_importance(model["Xte"], model["yte"])
    order = sorted(range(len(FEATURES)), key=lambda j: -mdi[j])
    perm_top = max(range(len(FEATURES)), key=lambda j: perm[j])
    ranking = [{"rank": r + 1, "feature": FEATURES[j], "label": LABELS[FEATURES[j]], "unit": UNITS[FEATURES[j]],
                "importance": round(mdi[j], 4), "importance_std": round(stds[j], 4),
                "permutation_importance": round(perm[j], 4)} for r, j in enumerate(order)]
    log.add("依 MDI 由大到小排序：" + " > ".join(f"{LABELS[FEATURES[j]]}({mdi[j]:.3f})" for j in order)
            + "。交叉檢查（測試集排列重要度＝打亂該特徵後準確率下降）：" + "、".join(f"{LABELS[f]} {v:+.3f}" for f, v in zip(FEATURES, perm))
            + f"，排列法最重要者為「{LABELS[FEATURES[perm_top]]}」。")

    # 5
    blocked_reasons = quality_problems(model)
    if blocked_reasons:
        return blocked("Guardrail 已攔截，不輸出排序", "BLOCKED_BY_GUARDRAIL (model quality)",
                       "為避免誤導，已拒絕輸出特徵重要度（模型本身不可靠）：" + "；".join(blocked_reasons), blocked_reasons)
    warnings = []
    top = order[0]
    if perm_top != top and perm[perm_top] - perm[top] > PERM_GAP:
        warnings.append(f"MDI 最重要的是「{LABELS[FEATURES[top]]}」，但排列重要度最高的是「{LABELS[FEATURES[perm_top]]}」，兩種方法明顯不一致，請謹慎解讀（MDI 偏向連續且取值多的特徵）")
    if mdi[top] > DOMINANCE_WARN:
        warnings.append(f"「{LABELS[FEATURES[top]]}」獨占 {mdi[top] * 100:.0f}% 的重要度，模型高度依賴單一參數")
    if mdi[top] < FLAT_WARN:
        warnings.append(f"最高的重要度僅 {mdi[top] * 100:.0f}%，沒有明顯的單一主因")
    if n < 30:
        warnings.append(f"樹數量僅 {n} 棵，重要度估計的隨機波動較大")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（測試集準確率 {model['holdout_accuracy'] * 100:.1f}% ≥ {MIN_HOLDOUT_ACC * 100:.0f}%、重要度總和為 1）。"
            + ("；".join(warnings) if warnings else ""))
    return finish({
        "status": "success", "found": True, "batch_id": batch_id, "n_trees": n,
        "feature_importance": ranking, "top_feature": FEATURES[top], "top_feature_label": LABELS[FEATURES[top]],
        "importance_sum": round(sum(mdi), 4), "data_source": model["source"],
        "model_metrics": {"oob_accuracy": round(model["oob_accuracy"], 4), "holdout_accuracy": round(model["holdout_accuracy"], 4)},
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"MDI 排名第一的製程參數是「{LABELS[FEATURES[top]]}」（重要度 {mdi[top]:.2f}），其次為「{LABELS[FEATURES[order[1]]]}」（{mdi[order[1]]:.2f}）。"
                       "這代表模型整體最依賴這個參數來區分良品與異常，不等同於單一批次的根因。",
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_15_feature_importance_ranking ===")
    print(json.dumps(rank_feature_importance("B-2026-10"), ensure_ascii=False, indent=2))
