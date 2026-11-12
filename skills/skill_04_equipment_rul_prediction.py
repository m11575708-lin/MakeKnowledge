"""
skill_04_equipment_rul_prediction.py - 設備剩餘使用壽命 (RUL) 預測技能

對應系統規格：US-03 / 06. 設備壽命預測頁
演算法機制：輸入防呆 -> Z-Score -> OLS 閉式解 β=(XᵀX)⁻¹Xᵀy（手寫高斯消去法）
            -> 預測與 holdout 評估 (MAE / RMSE / R²) -> 外插與模型品質 Guardrail

模型以 80/20 固定切分訓練與測試，MAE / RMSE 為「測試集」結果，避免用訓練資料自評。
僅使用 Python 標準庫。
"""

import json
import math
import random

try:
    from ._common import StepLog, default_output_path, save_json
    from .skill_03_sensor_data_preprocessing import (
        FEATURES, FEATURE_LABELS, FEATURE_UNITS, check_extrapolation, compute_zscore_stats,
        load_reference_dataset, validate_sensor_inputs, zscore_transform,
    )
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from skill_03_sensor_data_preprocessing import (
        FEATURES, FEATURE_LABELS, FEATURE_UNITS, check_extrapolation, compute_zscore_stats,
        load_reference_dataset, validate_sensor_inputs, zscore_transform,
    )

SKILL_NAME = "skill_04_equipment_rul_prediction"
MIN_R2 = 0.50          # 測試集 R² 低於此值，視為模型不可用
TEST_RATIO = 0.20
SPLIT_SEED = 7

PLAN = [
    ("輸入邊界與型別防呆", "Boundary & Type Validation", "math"),
    ("Z-Score 標準化（以訓練集統計量）", "Z-Score Standardization (StandardScaler)", "statistics, skill_03"),
    ("最小平方法閉式解求迴歸係數", "OLS Normal Equation (Gauss-Jordan Elimination)", "Python Built-in (純 list 矩陣運算)"),
    ("RUL 預測與測試集評估指標", "Multiple Linear Regression Prediction (MAE / RMSE / R²)", "math"),
    ("外插與模型品質 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


# ---------- 線性代數 ----------
def solve_linear_system(A: list, b: list) -> list:
    """高斯-約旦消去（部分選主元）。矩陣奇異時丟出 ValueError。"""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            raise ValueError("XᵀX 為奇異矩陣（特徵可能完全共線）")
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col]
                M[r] = [a - f * c for a, c in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


def ols_fit(X: list, y: list) -> list:
    """回傳 [截距, b1, b2, ...]。X 不含截距欄。"""
    Xa = [[1.0] + list(row) for row in X]
    p = len(Xa[0])
    XtX = [[sum(r[i] * r[j] for r in Xa) for j in range(p)] for i in range(p)]
    Xty = [sum(r[i] * yi for r, yi in zip(Xa, y)) for i in range(p)]
    return solve_linear_system(XtX, Xty)


# ---------- 模型 ----------
def fit_rul_model(csv_path: str = None) -> dict:
    rows, source = load_reference_dataset(csv_path)
    if len(rows) < len(FEATURES) + 10:
        raise ValueError("資料筆數不足以訓練模型")

    idx = list(range(len(rows)))
    random.Random(SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * TEST_RATIO))
    test = [rows[i] for i in idx[:n_test]]
    train = [rows[i] for i in idx[n_test:]]

    stats = compute_zscore_stats(train)
    X_train = [[zscore_transform(r, stats)[f] for f in FEATURES] for r in train]
    beta = ols_fit(X_train, [r["rul_hours"] for r in train])

    preds, errors = [], []
    for r in test:
        z = zscore_transform(r, stats)
        p = beta[0] + sum(beta[i + 1] * z[f] for i, f in enumerate(FEATURES))
        preds.append(p)
        errors.append(p - r["rul_hours"])
    y_test = [r["rul_hours"] for r in test]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    mean_y = sum(y_test) / len(y_test)
    ss_tot = sum((v - mean_y) ** 2 for v in y_test)
    r2 = 1 - sum(e * e for e in errors) / ss_tot if ss_tot > 0 else 0.0

    std_coefs = {f: beta[i + 1] for i, f in enumerate(FEATURES)}
    raw_coefs = {f: std_coefs[f] / stats[f]["std"] for f in FEATURES}
    raw_intercept = beta[0] - sum(std_coefs[f] * stats[f]["mean"] / stats[f]["std"] for f in FEATURES)

    return {
        "source": source, "stats": stats, "intercept_z": beta[0], "std_coefs": std_coefs,
        "raw_coefs": raw_coefs, "raw_intercept": raw_intercept,
        "metrics": {"mae": mae, "rmse": rmse, "r2": r2, "n_train": len(train), "n_test": len(test)},
        "max_rul": max(r["rul_hours"] for r in rows),
    }


def predict_with_model(model: dict, values: dict) -> float:
    z = zscore_transform(values, model["stats"])
    return model["intercept_z"] + sum(model["std_coefs"][f] * z[f] for f in FEATURES)


def _health_level(index_pct: float) -> str:
    if index_pct < 20:
        return "RED"
    if index_pct < 50:
        return "YELLOW"
    return "GREEN"


def _curve(model: dict, values: dict, points: int = 12) -> list:
    s = model["stats"]["operating_hours"]
    lo, hi = s["min"], s["max"]
    hrs = [lo + (hi - lo) * i / (points - 1) for i in range(points)]
    out = []
    for h in hrs:
        v = dict(values, operating_hours=h)
        out.append({"operating_hours": round(h, 1),
                    "predicted_rul_hours": round(max(0.0, predict_with_model(model, v)), 2)})
    return out


def predict_equipment_rul(
    operating_hours=1500, vibration=2.8, temperature=75, load_rate=85,
    output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("equipment_rul_prediction_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    raw = {"operating_hours": operating_hours, "vibration": vibration,
           "temperature": temperature, "load_rate": load_rate}

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    # 1. 輸入防呆
    values, errors = validate_sensor_inputs(raw)
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        log.skip_to_last("輸入未通過驗證")
        guardrail = "BLOCKED_BY_GUARDRAIL (invalid input)"
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "inputs": raw, "warnings": errors,
                       "guardrail_status": guardrail, "predicted_rul_hours": None,
                       "answer_text": "輸入未通過驗證：" + "；".join(errors)})
    log.add("4 個感測器欄位皆為有限數值且位於物理合理範圍內。")

    # 2~3. 訓練（含標準化、OLS）
    try:
        model = fit_rul_model()
    except ValueError as e:
        log.add(f"模型訓練失敗：{e}")
        log.skip_to_last("模型無法建立")
        guardrail = "BLOCKED_BY_GUARDRAIL (model unavailable)"
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "inputs": values, "warnings": [str(e)],
                       "guardrail_status": guardrail, "predicted_rul_hours": None,
                       "answer_text": f"無法建立預測模型：{e}"})

    st = model["stats"]
    m = model["metrics"]
    log.add(f"以訓練集 {m['n_train']} 筆（資料來源：{model['source']}）計算 μ、σ，並將本次輸入轉為 z 分數。")
    log.add("組成設計矩陣 X（含截距欄），求解 (XᵀX)β = Xᵀy 得 β："
            + "；".join(f"{f}: {model['std_coefs'][f]:+.2f}" for f in FEATURES)
            + f"；截距(標準化空間) {model['intercept_z']:.2f}。")

    # 4. 預測與評估
    raw_pred = predict_with_model(model, values)
    rul = max(0.0, raw_pred)
    interval = [max(0.0, rul - 1.96 * m["rmse"]), rul + 1.96 * m["rmse"]]
    index_pct = min(100.0, rul / model["max_rul"] * 100.0) if model["max_rul"] > 0 else 0.0
    level = _health_level(index_pct)
    log.add(f"ŷ = β₀ + Σβᵢzᵢ = {raw_pred:.1f} h" + ("（負值已截為 0）" if raw_pred < 0 else "")
            + f"。測試集 {m['n_test']} 筆：MAE={m['mae']:.2f}、RMSE={m['rmse']:.2f}、R²={m['r2']:.3f}。"
            f"健康度 {index_pct:.1f}%（<20% RED、<50% YELLOW、其餘 GREEN）。")

    # 5. Guardrail
    warnings, blocked = check_extrapolation(values, st)
    result_core = {
        "status": "success", "inputs": values, "data_source": model["source"],
        "eval_metrics": {"mae": round(m["mae"], 3), "rmse": round(m["rmse"], 3), "r2": round(m["r2"], 4),
                         "n_train": m["n_train"], "n_test": m["n_test"]},
        "intercept": round(model["raw_intercept"], 4),
        "regression_coefficients": {f: round(model["raw_coefs"][f], 5) for f in FEATURES},
        "standardized_coefficients": {f: round(model["std_coefs"][f], 4) for f in FEATURES},
    }
    if blocked or m["r2"] < MIN_R2:
        reasons = blocked + ([f"測試集 R²={m['r2']:.3f} < {MIN_R2}，模型品質不足"] if m["r2"] < MIN_R2 else [])
        guardrail = "BLOCKED_BY_GUARDRAIL (" + ("extrapolation" if blocked else "low model quality") + ")"
        log.add(f"防呆檢核狀態：{guardrail}。" + "；".join(reasons))
        return finish({**result_core, "found": False, "predicted_rul_hours": None,
                       "warnings": reasons + warnings, "guardrail_status": guardrail,
                       "answer_text": "為避免誤導，已拒絕輸出預測：" + "；".join(reasons)})

    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（R²={m['r2']:.3f} ≥ {MIN_R2}）。"
            + ("；".join(warnings) if warnings else "輸入皆在訓練資料範圍內。"))
    answer = (f"預估剩餘使用壽命約 {rul:.1f} 小時（約 {rul / 24:.1f} 天），"
              f"95% 區間 {interval[0]:.0f}–{interval[1]:.0f} 小時，健康度 {index_pct:.0f}%（{level}）。")
    return finish({
        **result_core, "found": True,
        "predicted_rul_hours": round(rul, 2),
        "prediction_interval": [round(interval[0], 2), round(interval[1], 2)],
        "health_index_pct": round(index_pct, 2), "health_level": level,
        "degradation_curve": _curve(model, values),
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_04_equipment_rul_prediction ===")
    res = predict_equipment_rul(1500, 2.8, 75, 85)
    res.pop("degradation_curve", None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
