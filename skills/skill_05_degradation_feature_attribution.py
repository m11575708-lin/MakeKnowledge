"""
skill_05_degradation_feature_attribution.py - 設備衰退特徵貢獻度拆解技能

對應系統規格：US-03 / 06. 設備壽命預測頁
演算法機制：重用 skill_04 的 OLS 模型 -> 原始/標準化係數 -> 本次輸入的逐特徵貢獻
            cᵢ = βᵢ·zᵢ（相對基準 RUL 的小時數）-> 佔比排序 -> Guardrail

解讀方式：
  基準 RUL (β₀) 是「所有特徵都等於訓練平均值」時的預測值；
  cᵢ 為 0 代表該特徵等於平均；負值代表該特徵讓 RUL 比基準更短（加速衰退）。
  預測值 ŷ = 基準 + Σcᵢ（未截斷時）。
"""

import json

try:
    from ._common import StepLog, default_output_path, save_json
    from .skill_03_sensor_data_preprocessing import (
        FEATURES, FEATURE_LABELS, FEATURE_UNITS, validate_sensor_inputs, zscore_transform,
    )
    from .skill_04_equipment_rul_prediction import MIN_R2, fit_rul_model
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from skill_03_sensor_data_preprocessing import (
        FEATURES, FEATURE_LABELS, FEATURE_UNITS, validate_sensor_inputs, zscore_transform,
    )
    from skill_04_equipment_rul_prediction import MIN_R2, fit_rul_model

SKILL_NAME = "skill_05_degradation_feature_attribution"

PLAN = [
    ("輸入防呆並載入 OLS 模型", "Boundary Validation & Model Reuse", "skill_03, skill_04"),
    ("迴歸係數拆解（原始單位 / 標準化）", "OLS Coefficient Decomposition", "Python Built-in"),
    ("逐特徵貢獻度計算", "Contribution Analysis cᵢ = βᵢ·zᵢ", "math"),
    ("貢獻佔比排序與主因判定", "Share-of-Impact Ranking", "Python Built-in Sorting"),
    ("Guardrail 檢核與歸因結論生成", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def attribute_degradation_features(
    operating_hours=1500, vibration=2.8, temperature=75, load_rate=85,
    output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("degradation_attribution_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    raw = {"operating_hours": operating_hours, "vibration": vibration,
           "temperature": temperature, "load_rate": load_rate}

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "contributions": [],
                       "warnings": warnings or [message], "guardrail_status": guardrail,
                       "answer_text": message})

    # 1. 防呆 + 模型
    values, errors = validate_sensor_inputs(raw)
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)
    try:
        model = fit_rul_model()
    except ValueError as e:
        log.add(f"輸入通過驗證，但模型訓練失敗：{e}")
        return blocked("模型無法建立", "BLOCKED_BY_GUARDRAIL (model unavailable)", f"無法建立模型：{e}")
    m = model["metrics"]
    log.add(f"輸入通過驗證；重用 skill_04 的 OLS 模型（資料來源：{model['source']}，訓練 {m['n_train']} 筆）。")

    # 2. 係數拆解
    log.add("原始單位係數 b = β_z / σ（每增加 1 單位對 RUL 的影響）："
            + "；".join(f"{f}: {model['raw_coefs'][f]:+.3f}/{FEATURE_UNITS[f]}" for f in FEATURES) + "。")

    # 3. 貢獻度
    z = zscore_transform(values, model["stats"])
    contribs = {f: model["std_coefs"][f] * z[f] for f in FEATURES}
    baseline = model["intercept_z"]
    log.add(f"基準 RUL（所有特徵＝平均）= {baseline:.1f} h；cᵢ = βᵢ·zᵢ："
            + "；".join(f"{f}: {contribs[f]:+.1f}h" for f in FEATURES) + "。")

    # 4. 排序與佔比
    total_abs = sum(abs(c) for c in contribs.values())
    rows = []
    for f in FEATURES:
        share = abs(contribs[f]) / total_abs * 100 if total_abs > 1e-9 else 0.0
        rows.append({
            "feature": f, "label": FEATURE_LABELS[f], "unit": FEATURE_UNITS[f],
            "value": values[f], "z_score": round(z[f], 4),
            "raw_coefficient": round(model["raw_coefs"][f], 5),
            "std_coefficient": round(model["std_coefs"][f], 4),
            "contribution_hours": round(contribs[f], 2),
            "share_pct": round(share, 2),
            "direction": "縮短壽命" if contribs[f] < 0 else ("延長壽命" if contribs[f] > 0 else "無影響"),
        })
    rows.sort(key=lambda r: r["share_pct"], reverse=True)
    log.add("依 |cᵢ| 佔 Σ|cⱼ| 的百分比降冪排序：" + "；".join(f"{r['label']} {r['share_pct']:.1f}%" for r in rows) + "。")

    # 5. Guardrail
    base_result = {
        "status": "success", "inputs": values, "data_source": model["source"],
        "baseline_rul_hours": round(baseline, 2),
        "regression_coefficients": {f: round(model["raw_coefs"][f], 5) for f in FEATURES},
        "standardized_coefficients": {f: round(model["std_coefs"][f], 4) for f in FEATURES},
        "contributions": rows,
    }
    if m["r2"] < MIN_R2:
        guardrail = "BLOCKED_BY_GUARDRAIL (low model quality)"
        log.add(f"防呆檢核狀態：{guardrail}。測試集 R²={m['r2']:.3f} < {MIN_R2}，係數不具解釋力。")
        return finish({**base_result, "found": False, "top_driver": None, "warnings": ["模型品質不足"],
                       "guardrail_status": guardrail,
                       "answer_text": "模型品質不足，貢獻度拆解不具參考價值。"})
    if total_abs < 1e-9:
        guardrail = "PASSED_NO_DEVIATION"
        log.add(f"防呆檢核狀態：{guardrail}。所有輸入恰等於訓練平均，無明顯主因。")
        return finish({**base_result, "found": True, "top_driver": None, "warnings": [],
                       "guardrail_status": guardrail, "answer_text": "本次輸入接近平均工況，沒有明顯的衰退主因。"})

    top = rows[0]
    guardrail = f"PASSED (R² {m['r2']:.3f} >= {MIN_R2})"
    log.add(f"防呆檢核狀態：{guardrail}。主因：{top['label']}（{top['direction']}，{top['contribution_hours']:+.1f}h）。")
    answer = (f"本次工況下最主要的影響因子是「{top['label']}」，使 RUL 相對基準{top['direction'].replace('壽命', '')}"
              f" {abs(top['contribution_hours']):.1f} 小時，佔總影響 {top['share_pct']:.0f}%。")
    return finish({**base_result, "found": True, "top_driver": top["feature"], "warnings": [],
                   "guardrail_status": guardrail, "answer_text": answer})


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_05_degradation_feature_attribution ===")
    print(json.dumps(attribute_degradation_features(1500, 2.8, 75, 85), ensure_ascii=False, indent=2))
