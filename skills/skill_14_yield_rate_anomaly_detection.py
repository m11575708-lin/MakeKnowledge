"""
skill_14_yield_rate_anomaly_detection.py - 隨機森林良率預測與品質異常分類技能

對應系統規格：US-09 / 10. 品質異常根本原因分析頁
演算法機制：輸入防呆 -> 載入資料與切分 -> Bootstrap + Gini 建立多棵決策樹
            -> 多樹投票與機率平均 -> Guardrail（模型品質／外插／投票邊界）

定義（請注意）：
  * 森林的訓練標籤為 0=良品、1=品質異常。
  * defect_probability = 所有樹葉節點不良比例的平均；yield_rate_prediction = 1 - defect_probability，
    是「模型估計的良品機率」，不是產線實測良率。批次若有實測良率（data/batches.csv）會另外並列，兩者不應混為一談。
  * ensemble_prediction = 多數決：超過半數的樹投 1 才判為異常。
  * 沒有 data/process_quality.csv 時使用固定 seed 的示範資料（synthetic_demo），規則是我自訂的。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._quality_data import FEATURES, LABELS, UNITS, clean_num
    from ._quality_model import get_model, quality_problems, resolve_batch, validate_n_trees, \
        MIN_HOLDOUT_ACC, MIN_OOB_ACC, TEST_RATIO
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _quality_data import FEATURES, LABELS, UNITS, clean_num
    from _quality_model import get_model, quality_problems, resolve_batch, validate_n_trees, \
        MIN_HOLDOUT_ACC, MIN_OOB_ACC, TEST_RATIO

SKILL_NAME = "skill_14_yield_rate_anomaly_detection"
BLOCK_Z, WARN_Z = 4.0, 3.0
BASELINE_MARGIN = 0.03     # 測試集準確率需勝過「永遠猜多數類」至少 3 個百分點
UNCERTAIN_BAND = (0.40, 0.60)
LOW_TREES_WARN = 30

PLAN = [
    ("批次參數與森林設定防呆", "Boundary & Type Validation", "math, re"),
    ("載入製程資料與訓練／測試切分", "Train/Test Holdout Split (80/20)", "csv, random"),
    ("Bootstrap 自助抽樣建立多棵決策樹", "Random Forest (Bootstrap + Gini Impurity)", "random"),
    ("多樹投票與良率機率平均", "Ensemble Majority Voting & Probability Averaging", "Python Built-in"),
    ("模型品質與外插 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def detect_yield_anomaly(batch_params=None, batch_id=None, n_trees: int = 100, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("yield_anomaly_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    echo = [clean_num(v) for v in batch_params] if isinstance(batch_params, (list, tuple)) else None

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "batch_id": batch_id, "batch_params": echo,
                       "yield_rate_prediction": None, "ensemble_prediction": None, "status_label": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1. 防呆
    n, n_err = validate_n_trees(n_trees)
    params, batch, errors, batches = resolve_batch(batch_id, batch_params)
    errors = list(errors or []) + ([n_err] if n_err else [])
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    echo = params
    src = f"批次 {batch['batch_id']} 的製程參數" if batch and batch_params is None else "使用者提供的參數"
    log.add(f"{src}：" + "、".join(f"{LABELS[f]} {v:g} {UNITS[f]}" for f, v in zip(FEATURES, params))
            + f"，皆為合理範圍內的有限數值；森林樹數量 N={n}（允許 10–300）。")

    # 2. 資料與切分（get_model 內完成；這裡先取得，第 3 步說明訓練）
    model = get_model(n)
    forest = model["forest"]
    log.add(f"資料來源：{model['source']}；共 {model['n_train'] + model['n_test']} 筆，不良率 {model['defect_rate'] * 100:.1f}%。"
            f"以固定 seed 切分：訓練 {model['n_train']} 筆、測試 {model['n_test']} 筆（{TEST_RATIO * 100:.0f}%，不參與訓練）。")

    # 3. 訓練
    depths = []
    def _depth(node):
        return 0 if node.feature is None else 1 + max(_depth(node.left), _depth(node.right))
    for t in forest.trees[:20]:
        depths.append(_depth(t.root))
    base_acc = max(model["defect_rate"], 1 - model["defect_rate"])
    log.add(f"建立 {n} 棵 CART 決策樹：每棵以 Bootstrap（有放回抽樣 {model['n_train']} 筆）訓練，每個節點僅隨機考慮 "
            f"{max(1, int(round(math.sqrt(len(FEATURES)))))} 個特徵，依吉尼不純度 I_G = 1 - Σp² 下降量最大者切分（最大深度 6、葉節點至少 5 筆；前 20 棵實際深度 {min(depths)}–{max(depths)}）。"
            f"OOB（袋外）準確率 {model['oob_accuracy'] * 100:.1f}%、測試集準確率 {model['holdout_accuracy'] * 100:.1f}%"
            f"（「永遠猜多數類」的基準為 {base_acc * 100:.1f}%）。")

    # 4. 投票
    p_defect, votes, total = forest.predict_detail(params)
    ensemble = 1 if votes > total / 2 else 0
    yield_pred = 1.0 - p_defect
    log.add(f"{total} 棵樹中 {votes} 棵投「異常」、{total - votes} 棵投「正常」（{votes / total * 100:.1f}%）；多數決（>50%）→ {ensemble}"
            f"（{'品質異常' if ensemble else '正常'}）。各樹葉節點不良比例平均 = {p_defect:.4f}，預估良率 = 1 - {p_defect:.4f} = {yield_pred * 100:.1f}%。")

    # 5. Guardrail
    blocked_reasons = quality_problems(model)
    if model["holdout_accuracy"] < base_acc + BASELINE_MARGIN:
        blocked_reasons.append(f"測試集準確率 {model['holdout_accuracy'] * 100:.1f}% 未明顯優於「永遠猜多數類」的 {base_acc * 100:.1f}%（需高出 {BASELINE_MARGIN * 100:.0f} 個百分點）")
    warnings = []
    for f, v in zip(FEATURES, params):
        st = model["stats"][f]
        z = (v - st["mean"]) / st["std"]
        desc = f"{LABELS[f]}={v:g}{UNITS[f]}"
        if abs(z) > BLOCK_Z:
            blocked_reasons.append(f"{desc} 的 |z|={abs(z):.2f} > {BLOCK_Z:g}，遠離訓練資料範圍")
        elif v < st["min"] or v > st["max"]:
            warnings.append(f"{desc} 超出訓練資料範圍 [{st['min']:.1f}, {st['max']:.1f}]，樹模型在範圍外只會沿用邊界葉節點，預測屬外插")
        elif abs(z) > WARN_Z:
            warnings.append(f"{desc} 的 |z|={abs(z):.2f} > {WARN_Z:g}")
    if blocked_reasons:
        kind = "extrapolation" if any("|z|" in r for r in blocked_reasons) else "model quality"
        return blocked("Guardrail 已攔截，不輸出預測", f"BLOCKED_BY_GUARDRAIL ({kind})",
                       "為避免誤導，已拒絕輸出良率預測：" + "；".join(blocked_reasons), blocked_reasons + warnings)
    frac = votes / total
    if UNCERTAIN_BAND[0] <= frac <= UNCERTAIN_BAND[1]:
        warnings.append(f"投票比例 {frac * 100:.0f}% 接近五五波，樹之間意見分歧，判定不穩定，建議人工複核")
    if n < LOW_TREES_WARN:
        warnings.append(f"樹數量僅 {n} 棵，投票結果的隨機波動較大（建議 ≥ {LOW_TREES_WARN}）")
    if model["recall"] is not None and model["recall"] < 0.6:
        warnings.append(f"測試集對異常批次的召回率僅 {model['recall'] * 100:.0f}%，可能漏判異常")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（OOB {model['oob_accuracy'] * 100:.1f}% ≥ {MIN_OOB_ACC * 100:.0f}%、測試集 {model['holdout_accuracy'] * 100:.1f}% ≥ {MIN_HOLDOUT_ACC * 100:.0f}% 且優於多數類基準、輸入未嚴重外插）。"
            + ("；".join(warnings) if warnings else ""))

    trend = []
    for b in batches:
        pd_, v, t = forest.predict_detail(b["params"])
        trend.append({"batch_id": b["batch_id"], "estimated_yield": round(1 - pd_, 4),
                      "observed_yield": b["yield_rate"], "anomaly_votes": v, "ensemble_prediction": 1 if v > t / 2 else 0,
                      "is_current": bool(batch and b["batch_id"] == batch["batch_id"])})
    answer = (f"預估良率 {yield_pred * 100:.1f}%，判定為「品質異常」（{votes}/{total} 棵樹投異常）。" if ensemble
              else f"預估良率 {yield_pred * 100:.1f}%，判定為「正常」（僅 {votes}/{total} 棵樹投異常）。")
    return finish({
        "status": "success", "found": True, "batch_id": batch["batch_id"] if batch else batch_id,
        "batch_params": params, "feature_names": FEATURES, "n_trees": n,
        "yield_rate_prediction": round(yield_pred, 4), "defect_probability": round(p_defect, 4),
        "ensemble_prediction": ensemble, "status_label": "QUALITY_ANOMALY" if ensemble else "NORMAL",
        "votes_anomaly": votes, "votes_total": total, "vote_fraction": round(frac, 4),
        "model_metrics": {"oob_accuracy": round(model["oob_accuracy"], 4), "holdout_accuracy": round(model["holdout_accuracy"], 4),
                          "majority_baseline": round(base_acc, 4), "recall": None if model["recall"] is None else round(model["recall"], 4),
                          "precision": None if model["precision"] is None else round(model["precision"], 4),
                          "n_train": model["n_train"], "n_test": model["n_test"], "defect_rate": round(model["defect_rate"], 4)},
        "batch_trend": trend, "data_source": model["source"],
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_14_yield_rate_anomaly_detection ===")
    print(json.dumps(detect_yield_anomaly([180.5, 42.0, 15.2]), ensure_ascii=False, indent=2))
