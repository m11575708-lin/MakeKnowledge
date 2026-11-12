"""
skill_08_cost_sensitive_threshold_tuning.py - 代價敏感預警門檻最佳化技能

對應系統規格：US-05 / 07. 設備突發故障風險評估頁
演算法機制：成本矩陣防呆 -> 載入測試集預測機率 -> 掃描門檻 θ∈[0,1] 統計 FN/FP
            -> 極小化 Cost(θ)=C_down·FN(θ)+C_inspect·FP(θ) -> 基準比較 Guardrail

判定規則：p ≥ θ 視為「預警並派工檢修」。
  FN = 實際故障但未預警（漏報，付停機損失）；FP = 實際正常卻預警（誤報，付檢修成本）。
評估資料為 skill_06 模型的測試集（未參與訓練）。門檻在同一測試集上挑選，
故最低成本略為樂觀；正式使用請另備驗證資料。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._failure_model import clean_num, fit_failure_model
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _failure_model import clean_num, fit_failure_model

SKILL_NAME = "skill_08_cost_sensitive_threshold_tuning"
MAX_COST = 1e9
EXTREME_RATIO = 1000.0

PLAN = [
    ("成本矩陣與掃描參數防呆", "Boundary & Type Validation", "math"),
    ("載入測試集預測機率與真實標籤", "Out-of-sample Probability Evaluation", "skill_06 模型 (純標準庫)"),
    ("掃描門檻並統計 FN / FP", "Threshold Sweep & Confusion Counting", "Python Built-in"),
    ("極小化預期總成本求最佳門檻", "Cost-sensitive Tuning  min C_down·FN + C_inspect·FP", "Python Built-in"),
    ("基準比較 Guardrail 檢核與決策建議", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def _cost_at(probs: list, labels: list, theta: float, c_down: float, c_insp: float) -> dict:
    fn = sum(1 for p, y in zip(probs, labels) if y == 1 and p < theta)
    fp = sum(1 for p, y in zip(probs, labels) if y == 0 and p >= theta)
    tp = sum(1 for p, y in zip(probs, labels) if y == 1 and p >= theta)
    tn = len(labels) - fn - fp - tp
    return {"threshold": round(theta, 4), "fn": fn, "fp": fp, "tp": tp, "tn": tn,
            "downtime_cost": c_down * fn, "inspection_cost": c_insp * fp,
            "total_cost": c_down * fn + c_insp * fp}


def tune_cost_threshold(
    cost_downtime=50000, cost_inspection=2000, failure_probability=None, step=0.01,
    output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("cost_threshold_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    echo = {"cost_downtime": clean_num(cost_downtime), "cost_inspection": clean_num(cost_inspection)}

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, **echo, "optimal_threshold": None,
                       "total_cost_min": None, "warnings": warnings or [message],
                       "guardrail_status": guardrail, "answer_text": message})

    # 1. 防呆
    errors = []
    for name, v in (("停機損失成本 cost_downtime", cost_downtime), ("誤報檢修成本 cost_inspection", cost_inspection)):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{name} 必須為數值")
        elif not math.isfinite(v):
            errors.append(f"{name} 不可為 NaN 或無限大")
        elif not 0 < v <= MAX_COST:
            errors.append(f"{name} = {v:g} 必須大於 0 且不超過 {MAX_COST:g}")
    if isinstance(step, bool) or not isinstance(step, (int, float)) or not math.isfinite(step) or not 0.001 <= step <= 0.1:
        errors.append("掃描間距 step 必須介於 0.001 到 0.1")
    p_now = None
    if failure_probability is not None:
        if (isinstance(failure_probability, bool) or not isinstance(failure_probability, (int, float))
                or not math.isfinite(failure_probability) or not 0.0 <= failure_probability <= 1.0):
            errors.append("failure_probability 若提供，必須是 0 到 1 之間的數值")
        else:
            p_now = float(failure_probability)
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)
    c_down, c_insp = float(cost_downtime), float(cost_inspection)
    ratio = c_down / c_insp
    log.add(f"成本矩陣：停機損失 C_down={c_down:,.0f}、誤報檢修 C_inspect={c_insp:,.0f}，"
            f"成本比 {ratio:.1f}:1；掃描間距 {step:g}。")

    # 2. 載入評估資料
    try:
        model = fit_failure_model()
    except ValueError as e:
        log.add(f"載入或擬合失敗：{e}")
        return blocked("評估資料無法建立", "BLOCKED_BY_GUARDRAIL (model unavailable)", f"無法建立評估資料：{e}")
    probs, labels, m = model["test_probs"], model["test_labels"], model["metrics"]
    if m["n_pos_test"] == 0 or m["n_neg_test"] == 0:
        log.add(f"測試集只有單一類別（故障 {m['n_pos_test']} / 正常 {m['n_neg_test']}），無法計算 FN / FP 取捨。")
        return blocked("測試集缺少某一類別", "BLOCKED_BY_GUARDRAIL (single-class evaluation set)",
                       "測試集只含單一類別，無法進行成本取捨。請補充歷史資料。")
    log.add(f"自 {model['source']} 取得測試集 {m['n_test']} 筆預測機率（故障 {m['n_pos_test']} / 正常 {m['n_neg_test']}），"
            f"皆為模型未見過的資料；測試集 AUC={m['auc']:.3f}。")

    # 3. 掃描
    n_steps = int(round(1.0 / step))
    thetas = [min(1.0, i * step) for i in range(n_steps + 1)]
    if thetas[-1] < 1.0:
        thetas.append(1.0)
    curve = [_cost_at(probs, labels, t, c_down, c_insp) for t in thetas]
    log.add(f"掃描 {len(curve)} 個門檻 θ ∈ [0, 1]；每個 θ 以「p ≥ θ 即預警」統計 FN（漏報）與 FP（誤報）。"
            f"θ=0 時全數預警（FP={m['n_neg_test']}），θ=1 時全不預警（FN={m['n_pos_test']}）。")

    # 4. 極小化
    min_cost = min(r["total_cost"] for r in curve)
    plateau = [r for r in curve if abs(r["total_cost"] - min_cost) < 1e-9]
    best = plateau[len(plateau) // 2]
    plateau_range = [plateau[0]["threshold"], plateau[-1]["threshold"]]
    log.add(f"Cost(θ)=C_down·FN+C_inspect·FP 的最小值為 {min_cost:,.0f}，出現於 θ ∈ [{plateau_range[0]:g}, {plateau_range[1]:g}]"
            f"（共 {len(plateau)} 個等價門檻）；取中位數 θ*={best['threshold']:g}（FN={best['fn']}、FP={best['fp']}）。")

    # 5. Guardrail：基準比較
    def at(theta):
        return min(curve, key=lambda r: abs(r["threshold"] - theta))
    never = _cost_at(probs, labels, 1.01, c_down, c_insp)    # 完全不預警
    always = _cost_at(probs, labels, 0.0, c_down, c_insp)    # 全部預警
    default_half = at(0.5)
    theory = c_insp / (c_insp + c_down)
    baselines = [
        {"name": "最佳門檻", "threshold": best["threshold"], "total_cost": best["total_cost"], "fn": best["fn"], "fp": best["fp"]},
        {"name": "預設門檻 0.5", "threshold": 0.5, "total_cost": default_half["total_cost"], "fn": default_half["fn"], "fp": default_half["fp"]},
        {"name": "完全不預警", "threshold": None, "total_cost": never["total_cost"], "fn": never["fn"], "fp": never["fp"]},
        {"name": "全部派工檢修", "threshold": 0.0, "total_cost": always["total_cost"], "fn": always["fn"], "fp": always["fp"]},
    ]
    best_baseline = min(b["total_cost"] for b in baselines[2:])
    saving_vs_best_trivial = best_baseline - best["total_cost"]
    warnings = ["最佳門檻是在同一測試集上挑選，最低成本略為樂觀；正式使用請另備驗證資料。"]
    if ratio >= EXTREME_RATIO or ratio <= 1 / EXTREME_RATIO:
        warnings.append(f"成本比 {ratio:.3g}:1 極端，最佳策略趨近「全部檢修」或「完全不預警」，請確認成本輸入。")
    if best["threshold"] in (0.0, 1.0):
        warnings.append(f"最佳門檻落在邊界 {best['threshold']:g}，代表在此成本下預警模型沒有帶來價值。")
    elif saving_vs_best_trivial <= 0:
        warnings.append("最佳門檻的成本不優於「完全不預警 / 全部檢修」的簡單策略，預警模型在此成本下沒有帶來價值。")
    if abs(best["threshold"] - theory) > 0.15:
        warnings.append(f"掃描最佳門檻 {best['threshold']:g} 與理論值 C_inspect/(C_inspect+C_down)={theory:.3f} 相差較大，"
                        "可能因測試集樣本不足或模型機率校準不佳。")
    guardrail = "PASSED" if len(warnings) == 1 else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}。對照：0.5 門檻成本 {default_half['total_cost']:,.0f}、"
            f"完全不預警 {never['total_cost']:,.0f}、全部檢修 {always['total_cost']:,.0f}；"
            f"成本取捨的理論門檻 {theory:.3f}。")

    decision = None
    if p_now is not None:
        alert = p_now >= best["threshold"]
        decision = {
            "failure_probability": round(p_now, 4), "optimal_threshold": best["threshold"], "alert": alert,
            "action": "派工檢修" if alert else "持續監控",
            "expected_downtime_loss": round(p_now * c_down, 2),
            "expected_inspection_cost_if_normal": round((1 - p_now) * c_insp, 2),
        }
    answer = (f"在停機損失 {c_down:,.0f}、誤報檢修 {c_insp:,.0f} 的成本下，最佳預警門檻為 {best['threshold']:g}，"
              f"測試集最低總成本 {min_cost:,.0f}（平均每台 {min_cost / m['n_test']:,.0f}）。")
    if decision:
        answer += f"目前故障機率 {p_now:.2f} {'≥' if decision['alert'] else '<'} 門檻，建議{decision['action']}。"

    return finish({
        "status": "success", "found": True, **echo, "data_source": model["source"],
        "optimal_threshold": best["threshold"], "optimal_threshold_range": plateau_range,
        "total_cost_min": round(min_cost, 2), "cost_per_equipment": round(min_cost / m["n_test"], 2),
        "n_eval": m["n_test"], "n_eval_failures": m["n_pos_test"],
        "theoretical_threshold": round(theory, 4), "cost_ratio": round(ratio, 3),
        "optimal_confusion": {k: best[k] for k in ("tp", "fp", "fn", "tn")},
        "baselines": baselines, "saving_vs_best_trivial": round(saving_vs_best_trivial, 2),
        "threshold_curve": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in curve],
        "decision": decision, "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_08_cost_sensitive_threshold_tuning ===")
    res = tune_cost_threshold(50000, 2000, 0.84)
    res.pop("threshold_curve", None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
