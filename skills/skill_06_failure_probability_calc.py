"""
skill_06_failure_probability_calc.py - 設備突發故障機率計算技能

對應系統規格：US-04 / 07. 設備突發故障風險評估頁
演算法機制：輸入防呆 -> 歷史資料載入與 80/20 切分 -> 邏輯迴歸 IRLS 牛頓法擬合
            -> Sigmoid 機率轉換 -> 外插與模型品質 Guardrail

P(Y=1) = 1 / (1 + e^-(wᵀx + b))；特徵先 Z-Score 標準化。
AUC / Accuracy / Log-loss 皆為未參與訓練的「測試集」結果。
資料來源：data/failure_history.csv；不存在時使用固定 seed 的示範合成資料（非真實設備紀錄）。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._failure_model import (
        FEATURES, FEATURE_LABELS, FEATURE_UNITS, MIN_AUC, check_extrapolation, clean_num,
        fit_failure_model, linear_score, sigmoid, validate_inputs, zscores,
    )
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _failure_model import (
        FEATURES, FEATURE_LABELS, FEATURE_UNITS, MIN_AUC, check_extrapolation, clean_num,
        fit_failure_model, linear_score, sigmoid, validate_inputs, zscores,
    )

SKILL_NAME = "skill_06_failure_probability_calc"

PLAN = [
    ("輸入邊界與型別防呆", "Boundary & Type Validation", "math"),
    ("載入歷史資料並切分訓練 / 測試集", "Dataset Loader & 80/20 Holdout Split", "csv, random"),
    ("邏輯迴歸係數擬合（牛頓法 IRLS）", "Logistic Regression (Newton-Raphson / IRLS)", "Python Built-in (純 list 矩陣運算)"),
    ("Sigmoid 機率轉換", "Sigmoid P(Y=1)=1/(1+e^-(wᵀx+b))", "math"),
    ("外插與模型品質 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def _sigmoid_curve(z_now: float, lo: float = -7.0, hi: float = 7.0, points: int = 29) -> list:
    zs = sorted({lo + (hi - lo) * i / (points - 1) for i in range(points)} | {z_now})
    return [{"z": round(z, 3), "probability": round(sigmoid(z), 5)} for z in zs]


def calculate_failure_probability(
    recency_days=45, alarms_90d=12, pressure=1.8, output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("failure_probability_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    raw = {"recency_days": recency_days, "alarms_90d": alarms_90d, "pressure": pressure}
    echo = {f: clean_num(raw[f]) for f in FEATURES}

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None, extra=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "inputs": echo,
                       "failure_probability": None, "warnings": warnings or [message],
                       "guardrail_status": guardrail, "answer_text": message, **(extra or {})})

    # 1. 輸入防呆
    values, errors = validate_inputs(raw)
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)
    log.add("3 個欄位皆為有限數值、位於物理合理範圍內，且警報次數為整數。")

    # 2~3. 載入 + 擬合
    try:
        model = fit_failure_model()
    except ValueError as e:
        log.add(f"載入或擬合失敗：{e}")
        return blocked("模型無法建立", "BLOCKED_BY_GUARDRAIL (model unavailable)", f"無法建立預測模型：{e}")
    m = model["metrics"]
    log.add(f"自 {model['source']} 載入資料，80/20 固定切分：訓練 {m['n_train']} 筆"
            f"（故障率 {m['prevalence_train'] * 100:.1f}%）、測試 {m['n_test']} 筆"
            f"（故障 {m['n_pos_test']} / 正常 {m['n_neg_test']}）。")
    log.add(f"IRLS 牛頓法 {model['iterations']} 次迭代{'收斂' if model['converged'] else '未收斂'}；"
            "標準化係數 β："
            + "；".join(f"{f}: {model['std_coefs'][f]:+.3f}" for f in FEATURES)
            + f"；截距 {model['intercept_z']:+.3f}。")

    # 4. Sigmoid
    z_score = linear_score(model, values)
    prob = sigmoid(z_score)
    zs = zscores(values, model["stats"])
    log.add(f"線性分數 z = wᵀx + b = {z_score:+.3f}；P(Y=1) = 1/(1+e^-z) = {prob:.4f}。"
            f"測試集 AUC={m['auc']:.3f}、Accuracy={m['accuracy']:.3f}、Log-loss={m['log_loss']:.3f}。")

    # 5. Guardrail
    warnings, blocked_reasons = check_extrapolation(values, model["stats"])
    odds_ratios = []
    for f in FEATURES:
        odds_ratios.append({
            "feature": f, "label": FEATURE_LABELS[f], "unit": FEATURE_UNITS[f],
            "value": values[f], "z_score": round(zs[f], 4),
            "raw_coefficient": round(model["raw_coefs"][f], 5),
            "std_coefficient": round(model["std_coefs"][f], 4),
            "odds_ratio_per_unit": round(math.exp(model["raw_coefs"][f]), 5),
            "odds_ratio_per_sd": round(math.exp(model["std_coefs"][f]), 4),
        })
    core = {
        "status": "success", "inputs": values, "data_source": model["source"],
        "linear_score": round(z_score, 4),
        "eval_metrics": {"auc": round(m["auc"], 4), "accuracy": round(m["accuracy"], 4),
                         "log_loss": round(m["log_loss"], 4), "n_train": m["n_train"], "n_test": m["n_test"],
                         "prevalence_train": round(m["prevalence_train"], 4)},
        "intercept": round(model["raw_intercept"], 5),
        "regression_coefficients": {f: round(model["raw_coefs"][f], 5) for f in FEATURES},
        "standardized_coefficients": {f: round(model["std_coefs"][f], 4) for f in FEATURES},
        "feature_odds_ratios": odds_ratios,
        "sigmoid_curve": _sigmoid_curve(z_score),
        "converged": model["converged"],
    }

    reasons = list(blocked_reasons)
    if m["auc"] < MIN_AUC:
        reasons.append(f"測試集 AUC={m['auc']:.3f} < {MIN_AUC}，模型鑑別力不足")
    if not model["converged"]:
        reasons.append("牛頓法未收斂，係數不可信")
    if reasons:
        kind = "extrapolation" if blocked_reasons else ("low model quality" if m["auc"] < MIN_AUC else "not converged")
        guardrail = f"BLOCKED_BY_GUARDRAIL ({kind})"
        log.add(f"防呆檢核狀態：{guardrail}。" + "；".join(reasons))
        return finish({**core, "found": False, "failure_probability": None,
                       "warnings": reasons + warnings, "guardrail_status": guardrail,
                       "answer_text": "為避免誤導，已拒絕輸出故障機率：" + "；".join(reasons)})

    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（AUC={m['auc']:.3f} ≥ {MIN_AUC}、已收斂）。"
            + ("；".join(warnings) if warnings else "輸入皆在訓練資料範圍內。"))
    return finish({**core, "found": True, "failure_probability": round(prob, 4),
                   "warnings": warnings, "guardrail_status": guardrail,
                   "answer_text": f"在目前工況下，設備發生突發故障的機率約為 {prob * 100:.1f}%。"})


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_06_failure_probability_calc ===")
    res = calculate_failure_probability(45, 12, 1.8)
    res.pop("sigmoid_curve", None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
