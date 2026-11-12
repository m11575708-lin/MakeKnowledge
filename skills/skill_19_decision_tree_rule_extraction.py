"""
skill_19_decision_tree_rule_extraction.py - 代價複雜度剪枝與白盒 IF-THEN 規則導出技能

對應系統規格：US-11. 鋼板表面缺陷分類與特徵評估頁
演算法機制：α 與前置檢核 -> 最弱連結剪枝序列 (g(t)) -> 選樹（使用者 α 或驗證集建議 α）
            -> 路徑轉 IF-THEN 規則 -> 測試集剪枝前後比較與 Guardrail

代價複雜度：R_α(T) = R(T) + α|T|，R(T) 為訓練集誤分類比例、|T| 為葉節點數。
  α=0 幾乎不剪（只剪不降低訓練誤差的切分）；α 越大，樹越小。這裡的 R 以「誤分類比例」計，所以 α 的合理範圍約 0–0.1，
  α 超過約 0.15 時樹會塌縮到只剩 1~2 個葉節點。

三份資料的分工（和規格「以測試集選 α」不同，請注意）：
  訓練集：長樹與計算 g(t)；驗證集：只用來建議 α；測試集：只用來報告剪枝前後準確率與混淆矩陣。
  （若用測試集選 α，再用同一份測試集報告準確率，會高估剪枝後的表現。）
  測試集只有約 120 筆，1 筆約等於 0.8 個百分點；剪枝前後差距小於 2 個百分點不具統計意義。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _cart as cart
    from ._steel_model import FEATURES, LABELS, clean_num, get_model, model_problems, validate_inputs
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _cart as cart
    from _steel_model import FEATURES, LABELS, clean_num, get_model, model_problems, validate_inputs

SKILL_NAME = "skill_19_decision_tree_rule_extraction"
ALPHA_MAX = 1.0
DROP_WARN = 0.05          # 剪枝後測試準確率下降超過 5 個百分點就警告
SMALL_RULE = 5            # 支持樣本少於 5 筆的規則視為不穩定
NOISE_PP = 0.02

PLAN = [
    ("剪枝係數 α 與輸入前置檢核", "Boundary & Type Validation", "math"),
    ("建立最弱連結剪枝序列", "Cost-Complexity Pruning (Weakest-link g(t))", "copy"),
    ("以驗證集建議 α 並選定剪枝後的樹", "Minimal Cost-Complexity Subtree  R_α(T)=R(T)+α|T|", "Python Built-in"),
    ("樹路徑轉白盒 IF-THEN 規則", "Rule Extraction from Root-to-Leaf Paths", "Python Built-in"),
    ("測試集剪枝前後比較與 Guardrail 檢核", "Held-out Test Evaluation & Guardrail", "Python Control Flow"),
]


def extract_decision_tree_rules(alpha_threshold=0.01, area=None, aspect_ratio=None, contrast=None,
                                auto_alpha: bool = False, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("decision_tree_rules_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None, extra=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "rules": [], "rule_path": None,
                       "pruning_status": "NOT_COMPLETED", "warnings": warnings or [message],
                       "guardrail_status": guardrail, "answer_text": message, **(extra or {})})

    # 1
    errors = []
    a = alpha_threshold
    if isinstance(a, bool) or not isinstance(a, (int, float)) or not math.isfinite(a):
        errors.append("α 必須為有限數值")
    elif not 0 <= a <= ALPHA_MAX:
        errors.append(f"α = {a:g} 超出範圍 [0, {ALPHA_MAX:g}]")
    vec = None
    given = [v is not None for v in (area, aspect_ratio, contrast)]
    if any(given):
        if not all(given):
            errors.append("要對單一缺陷比對規則時，面積、長寬比、對比度必須同時提供")
        else:
            vec, ferr = validate_inputs(area, aspect_ratio, contrast)
            errors += ferr
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    log.add(f"α = {a:g}（允許 0–{ALPHA_MAX:g}）；" + ("自動使用驗證集建議的 α。" if auto_alpha else "使用者指定 α。")
            + ("要比對的缺陷：" + "、".join(f"{LABELS[f]} {v:g}" for f, v in zip(FEATURES, vec)) + "。" if vec else "未提供單一缺陷，只導出整體規則。"))

    # 2
    model = get_model()
    k = len(model["classes"])
    seq = model["seq"]
    full = seq[0]["tree"]
    distinct = {}
    for item in seq:
        distinct[round(item["alpha"], 12)] = item          # 同一 α 取最後一棵（最小的樹）
    reachable = list(distinct.values())
    log.add(f"完整樹 {seq[0]['leaves']} 個葉節點。對每個內部節點 t 計算 g(t) = (R(t) - R(T_t)) / (|T_t| - 1)（R 為誤分類比例，N={len(model['Xtr'])}），"
            f"反覆剪掉 g 最小的節點，得到 {len(seq)} 棵巢狀子樹；其中不同 α 可到達的有 {len(reachable)} 棵，α 序列 "
            + " → ".join(f"{r['alpha']:.4f}({r['leaves']}葉)" for r in reachable[:6]) + (" …" if len(reachable) > 6 else "") + "（非遞減）。")

    # 3
    best = max(reachable, key=lambda r: (round(r["val_acc"], 12), r["alpha"]))
    if auto_alpha:
        chosen, alpha_used = best, best["alpha"]
    else:
        chosen, alpha_used = cart.pick_by_alpha(seq, a), a
    pruned = chosen["tree"]
    log.add(f"驗證集準確率最高的可到達子樹：α={best['alpha']:.4f}、{best['leaves']} 個葉節點、驗證準確率 {best['val_acc'] * 100:.1f}%（同分取較大 α＝較小的樹）→ 建議 α。"
            f"本次採用 α={alpha_used:.4f}，選出 {chosen['leaves']} 個葉節點的子樹（訓練 {chosen['train_acc'] * 100:.1f}%、驗證 {chosen['val_acc'] * 100:.1f}%）。")

    # 單葉樹：沒有規則可言
    if cart.is_leaf(pruned):
        log.add("α 過大，整棵樹被剪成只剩一個葉節點，不存在任何判斷規則。")
        return blocked("樹被剪光，無規則可導出", "BLOCKED_BY_GUARDRAIL (over-pruned)",
                       f"α={alpha_used:g} 過大，樹被剪成單一葉節點（只會一律預測 {model['classes'][cart.majority(pruned)]}），請調低 α",
                       extra={"alpha_used": alpha_used, "alpha_recommended": best["alpha"]})

    # 4
    rules = cart.extract_rules(pruned, FEATURES, model["classes"])
    te_counts = {id(r["_leaf"]): [0, 0] for r in rules}
    for xi, yi in zip(model["Xte"], model["yte"]):
        lf = cart.find_leaf(pruned, xi)
        te_counts[id(lf)][0] += 1
        te_counts[id(lf)][1] += (cart.majority(lf) == yi)
    matched_leaf = cart.find_leaf(pruned, vec) if vec else None
    out_rules = []
    for i, r in enumerate(rules):
        n_te, ok_te = te_counts[id(r["_leaf"])]
        out_rules.append({"rule_id": i + 1, "text": r["text"], "conditions": r["conditions"], "class": r["class"],
                          "class_label": model["class_labels"][r["class_index"]], "train_samples": r["n"],
                          "train_purity": round(r["purity"], 4), "test_samples": n_te,
                          "test_accuracy": round(ok_te / n_te, 4) if n_te else None,
                          "matched": matched_leaf is not None and r["_leaf"] is matched_leaf})
    rule_path = next((r["text"] for r, o in zip(rules, out_rules) if o["matched"]), None)
    log.add(f"剪枝後的樹有 {len(rules)} 個葉節點，對應 {len(rules)} 條規則；每條根到葉的路徑轉成 IF-THEN，同一特徵的多個條件合併為最緊的上下界。"
            + (f"本次缺陷符合：{rule_path}。" if rule_path else ""))

    # 5
    acc_before = cart.accuracy(full, model["Xte"], model["yte"])
    acc_after = cart.accuracy(pruned, model["Xte"], model["yte"])
    cm_before = cart.confusion_matrix(full, model["Xte"], model["yte"], k)
    cm_after = cart.confusion_matrix(pruned, model["Xte"], model["yte"], k)
    problems = model_problems(model, pruned)
    never = [model["classes"][c] for c in range(k) if not any(r["class_index"] == c for r in rules)]
    cmp_text = (f"測試集（{len(model['yte'])} 筆，未參與選 α）：剪枝前 {acc_before * 100:.1f}%（{seq[0]['leaves']} 葉）→ 剪枝後 {acc_after * 100:.1f}%（{chosen['leaves']} 葉），"
                f"差 {(acc_after - acc_before) * 100:+.1f} 個百分點。")
    if problems:
        log.add(cmp_text + "防呆檢核狀態：BLOCKED_BY_GUARDRAIL (model quality)。")
        return finish({"status": "success", "found": False, "rules": [], "rule_path": None, "pruning_status": "NOT_COMPLETED",
                       "warnings": problems, "guardrail_status": "BLOCKED_BY_GUARDRAIL (model quality)",
                       "answer_text": "剪枝後的模型不可靠，已拒絕輸出規則：" + "；".join(problems),
                       "alpha_used": alpha_used, "alpha_recommended": best["alpha"]})
    warnings = []
    if acc_before - acc_after > DROP_WARN:
        warnings.append(f"剪枝後測試準確率下降 {(acc_before - acc_after) * 100:.1f} 個百分點（> {DROP_WARN * 100:.0f}），α 可能過大")
    if never:
        warnings.append(f"剪枝後的樹已不會預測「{'、'.join(never)}」類，這些缺陷會被歸到其他類別")
    weak = [o["rule_id"] for o in out_rules if o["train_samples"] < SMALL_RULE]
    if weak:
        warnings.append(f"規則 {', '.join(map(str, weak))} 的訓練支持樣本少於 {SMALL_RULE} 筆，不穩定")
    if abs(acc_after - acc_before) < NOISE_PP:
        warnings.append(f"剪枝前後測試準確率差距小於 {NOISE_PP * 100:.0f} 個百分點，在測試集 {len(model['yte'])} 筆的雜訊範圍內，不能說剪枝有變好或變差，但規則更精簡")
    if vec is not None:
        for f, v in zip(FEATURES, vec):
            st = model["stats"][f]
            if v < st["min"] or v > st["max"]:
                warnings.append(f"{LABELS[f]}={v:g} 超出訓練資料範圍，規則比對屬外插")
    real = [w for w in warnings if "雜訊範圍" not in w]
    guardrail = "PASSED" if not real else "PASSED_WITH_WARNINGS"
    log.add(cmp_text + f"防呆檢核狀態：{guardrail}（剪枝後模型品質通過）。" + ("；".join(warnings) if warnings else ""))

    pred_after = None
    if vec:
        lf = cart.find_leaf(pruned, vec)
        pred_after = model["classes"][cart.majority(lf)]
    curve = [{"alpha": round(r["alpha"], 5), "leaves": r["leaves"], "train_accuracy": round(r["train_acc"], 4),
              "val_accuracy": round(r["val_acc"], 4)} for r in reachable]
    return finish({
        "status": "success", "found": True, "pruning_status": "COMPLETED",
        "alpha_used": round(alpha_used, 5), "alpha_recommended": round(best["alpha"], 5), "auto_alpha": bool(auto_alpha),
        "rule_path": rule_path, "pruned_defect_class": pred_after, "rules": out_rules,
        "accuracy_before": round(acc_before, 4), "accuracy_after": round(acc_after, 4),
        "accuracy_validation_after": round(chosen["val_acc"], 4), "accuracy_train_after": round(chosen["train_acc"], 4),
        "leaves_before": seq[0]["leaves"], "leaves_after": chosen["leaves"],
        "confusion_matrix_before": cm_before, "confusion_matrix_after": cm_after,
        "class_names": model["classes"], "class_labels": model["class_labels"],
        "alpha_curve": curve, "n_test": len(model["yte"]),
        "tree": cart.to_json_tree(pruned, FEATURES, model["classes"], vec),
        "data_source": model["source"], "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": (f"剪枝後保留 {chosen['leaves']} 個葉節點（原 {seq[0]['leaves']}），共 {len(rules)} 條規則；測試集準確率 {acc_before * 100:.1f}% → {acc_after * 100:.1f}%。"
                        + (f"本次缺陷符合：{rule_path}。" if rule_path else "")),
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_19_decision_tree_rule_extraction ===")
    r = extract_decision_tree_rules(0.01, 150, 4.2, 85)
    r.pop("tree", None)
    print(json.dumps(r, ensure_ascii=False, indent=2))
