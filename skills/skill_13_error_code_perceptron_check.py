"""
skill_13_error_code_perceptron_check.py - 單層感知器即時合規二元驗證技能

對應系統規格：US-08 / 09. 維修案例登錄與故障碼驗證頁
演算法機制：輸入防呆 -> 載入（或訓練）感知器狀態 -> Guardrail 前置評估
            -> 線性超平面劃分 f(x)=step(wᵀz+b) -> 錯誤驅動單點權重更新 w ← w + η(y-ŷ)z

標籤約定：0 = 合規 (COMPLIANT)，1 = 異常 (NON_COMPLIANT)。score > 0 判為 1，否則判為 0。
特徵先以訓練集的平均與標準差 Z-Score 標準化；顯示的 w1, w2, bias 是「標準化空間」的權重。

重要說明：
  * 專案沒有真實的「合規/異常」標註資料。找不到 data/repair_compliance.csv
    （欄位 current_a,pressure_mpa,label）時，使用固定 seed 的「示範規則」合成資料訓練——
    規則是我設定的示範（高電流且高壓力的組合視為異常），不是任何真實的合規標準。
  * 感知器只在「使用者提供人工確認結果 confirmed_label，且與預測不符」時更新權重；
    沒有確認結果就不會學習。權重狀態存於 data/perceptron_state.json，可用 reset_perceptron_model() 還原。
  * 感知器只能處理線性可分的資料，且輸出的是硬判定、不是機率。
"""

import csv
import hashlib
import json
import math
import os
import random
from datetime import datetime

try:
    from ._common import StepLog, default_output_path, save_json
    from ._repair_data import clean_num
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _repair_data import clean_num

SKILL_NAME = "skill_13_error_code_perceptron_check"
FEATURES = ["current_a", "pressure_mpa"]
FEATURE_LABELS = {"current_a": "即時電流", "pressure_mpa": "即時壓力"}
FEATURE_UNITS = {"current_a": "A", "pressure_mpa": "MPa"}
HARD_LIMITS = {"current_a": (0.0, 500.0), "pressure_mpa": (0.0, 30.0)}

ETA = 0.1
MAX_EPOCHS = 200
TEST_RATIO = 0.20
SPLIT_SEED = 5
MIN_HOLDOUT_ACC = 0.90
MAX_UPDATES = 500
BLOCK_Z, WARN_Z = 4.0, 3.0
NEAR_BOUNDARY = 0.25      # 距離超平面（z 空間）小於此值視為接近邊界
LOG_KEEP = 20
PLOT_POINTS = 150

PLAN = [
    ("輸入特徵與人工確認結果防呆", "Boundary & Type Validation", "math"),
    ("載入或訓練感知器狀態", "Perceptron Learning Rule (Mistake-driven Training)", "csv, json, random"),
    ("線性超平面劃分", "Linear Hyperplane Classification  f(x)=step(wᵀz+b)", "Python Built-in"),
    ("錯誤驅動單點權重更新", "Perceptron Online Update  w ← w + η(y-ŷ)z", "Python Built-in"),
    ("模型品質與外插 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


# ---------- 資料與訓練 ----------
def generate_reference_dataset(n: int = 400, seed: int = 21) -> list:
    """示範規則：s = 0.8·(電流-45)/20 + 1.0·(壓力-1.8)/0.7；s>1 為異常。排除邊界附近 |s-1|<0.3 的點，確保線性可分。"""
    rng = random.Random(seed)
    rows = []
    while len(rows) < n:
        cur, pr = rng.uniform(15, 95), rng.uniform(0.4, 3.6)
        s = 0.8 * (cur - 45) / 20 + 1.0 * (pr - 1.8) / 0.7
        if abs(s - 1.0) < 0.3:
            continue
        rows.append({"current_a": cur, "pressure_mpa": pr, "label": 1 if s > 1.0 else 0})
    return rows


def load_reference_dataset(csv_path: str = None):
    path = csv_path or default_output_path("repair_compliance.csv")
    if os.path.exists(path):
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                needed = FEATURES + ["label"]
                if not reader.fieldnames or not set(needed) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {needed}")
                for rec in reader:
                    row = {k: float(rec[k]) for k in needed}
                    if row["label"] not in (0.0, 1.0):
                        raise ValueError("label 只能是 0 或 1")
                    row["label"] = int(row["label"])
                    if not all(math.isfinite(row[k]) for k in FEATURES):
                        raise ValueError("特徵必須是有限數值")
                    rows.append(row)
            if len(rows) < 40 or len({r["label"] for r in rows}) < 2:
                raise ValueError("至少需要 40 筆資料且兩個類別都要有")
            return rows, "data/repair_compliance.csv"
        except Exception as e:
            print(f"讀取 repair_compliance.csv 失敗：{e}，改用示範規則資料", flush=True)
    return generate_reference_dataset(), "synthetic_demo_rule (seed=21，示範規則非真實標準)"


def _signature(rows: list, source: str) -> str:
    blob = source + "|" + ",".join(f"{r['current_a']:.4f}:{r['pressure_mpa']:.4f}:{r['label']}" for r in rows)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _train(train: list, mean: list, std: list, eta: float = ETA, max_epochs: int = MAX_EPOCHS):
    """感知器學習規則；回傳 (w, b, epochs, converged, total_mistakes)。"""
    w, b, total = [0.0, 0.0], 0.0, 0
    zs = [([(r[FEATURES[0]] - mean[0]) / std[0], (r[FEATURES[1]] - mean[1]) / std[1]], r["label"]) for r in train]
    for epoch in range(1, max_epochs + 1):
        mistakes = 0
        for z, y in zs:
            pred = 1 if (w[0] * z[0] + w[1] * z[1] + b) > 0 else 0
            if pred != y:
                w[0] += eta * (y - pred) * z[0]
                w[1] += eta * (y - pred) * z[1]
                b += eta * (y - pred)
                mistakes += 1
        total += mistakes
        if mistakes == 0:
            return w, b, epoch, True, total
    return w, b, max_epochs, False, total


def _accuracy(rows: list, w, b, mean, std) -> float:
    ok = 0
    for r in rows:
        z = [(r[FEATURES[0]] - mean[0]) / std[0], (r[FEATURES[1]] - mean[1]) / std[1]]
        ok += (1 if (w[0] * z[0] + w[1] * z[1] + b) > 0 else 0) == r["label"]
    return ok / len(rows)


def build_state() -> dict:
    rows, source = load_reference_dataset()
    idx = list(range(len(rows)))
    random.Random(SPLIT_SEED).shuffle(idx)
    n_test = max(1, int(len(rows) * TEST_RATIO))
    test = [rows[i] for i in idx[:n_test]]
    train = [rows[i] for i in idx[n_test:]]
    mean, std = [], []
    for f in FEATURES:
        vals = [r[f] for r in train]
        m = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
        if sd <= 0:
            raise ValueError(f"特徵 {f} 的標準差為 0，無法標準化")
        mean.append(m); std.append(sd)
    order = list(range(len(train)))
    random.Random(SPLIT_SEED + 1).shuffle(order)
    w, b, epochs, converged, mistakes = _train([train[i] for i in order], mean, std)
    plot_rows = rows if len(rows) <= PLOT_POINTS else random.Random(3).sample(rows, PLOT_POINTS)
    return {
        "version": 1, "signature": _signature(rows, source), "source": source, "eta": ETA,
        "w": w, "b": b, "mean": mean, "std": std, "n_updates": 0, "update_log": [],
        "ranges": {f: [min(r[f] for r in train), max(r[f] for r in train)] for f in FEATURES},
        "metrics": {"epochs": epochs, "converged": converged, "train_mistakes": mistakes,
                    "n_train": len(train), "n_test": len(test),
                    "train_accuracy": _accuracy(train, w, b, mean, std),
                    "holdout_accuracy": _accuracy(test, w, b, mean, std),
                    "prevalence": sum(r["label"] for r in rows) / len(rows)},
        "plot_points": [{"x": round(r["current_a"], 2), "y": round(r["pressure_mpa"], 3), "label": r["label"]} for r in plot_rows],
    }


def _state_path() -> str:
    return default_output_path("perceptron_state.json")


def load_state():
    """回傳 (state, origin)；origin 為 'loaded' / 'trained'。狀態檔損毀或資料來源改變時自動重訓。"""
    path = _state_path()
    rows_sig = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
            rows, source = load_reference_dataset()
            rows_sig = _signature(rows, source)
            if (st.get("version") == 1 and st.get("signature") == rows_sig
                    and len(st["w"]) == 2 and all(math.isfinite(v) for v in st["w"] + [st["b"]])):
                return st, "loaded"
        except Exception as e:
            print(f"感知器狀態檔無法使用：{e}，重新訓練", flush=True)
    st = build_state()
    save_json(st, path)
    return st, "trained"


def reset_perceptron_model() -> dict:
    """刪除已學習的權重並重新訓練。"""
    path = _state_path()
    if os.path.exists(path):
        os.remove(path)
    st = build_state()
    save_json(st, path)
    return {"status": "success", "found": True, "answer_text": "感知器已還原為初始訓練結果。",
            "updated_weights": {"w1": round(st["w"][0], 4), "w2": round(st["w"][1], 4), "bias": round(st["b"], 4)},
            "metrics": st["metrics"], "steps": []}


# ---------- 輔助 ----------
def _score(state: dict, z: list) -> float:
    return state["w"][0] * z[0] + state["w"][1] * z[1] + state["b"]


def _weights_dict(w, b) -> dict:
    return {"w1": round(w[0], 4), "w2": round(w[1], 4), "bias": round(b, 4)}


def _boundary_line(state: dict, x_lo: float, x_hi: float, y_lo: float, y_hi: float):
    """超平面在原始單位的線段端點（供前端繪圖；前端以 clipPath 裁切）。"""
    (w1, w2), b = state["w"], state["b"]
    m, s = state["mean"], state["std"]
    if abs(w2) > 1e-9:
        pts = []
        for x in (x_lo, x_hi):
            z1 = (x - m[0]) / s[0]
            z2 = -(b + w1 * z1) / w2
            pts.append([round(x, 3), round(m[1] + s[1] * z2, 3)])
        return pts
    if abs(w1) > 1e-9:
        x = m[0] + s[0] * (-b / w1)
        return [[round(x, 3), y_lo], [round(x, 3), y_hi]]
    return None


def check_error_code_perceptron(features=None, confirmed_label=None, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("perceptron_check_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    echo = [clean_num(v) for v in features] if isinstance(features, (list, tuple)) else None

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None, extra=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "features": echo, "validation_result": None,
                       "status_label": None, "warnings": warnings or [message], "guardrail_status": guardrail,
                       "answer_text": message, **(extra or {})})

    # 1. 防呆
    errors = []
    if features is None:
        errors.append("缺少 features（前一步欄位驗證可能未通過）")
        vec = None
    elif not isinstance(features, (list, tuple)) or len(features) != len(FEATURES):
        errors.append(f"features 需要 {len(FEATURES)} 個數值（{', '.join(FEATURES)}）")
        vec = None
    else:
        vec = []
        for f, v in zip(FEATURES, features):
            label = FEATURE_LABELS[f]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                errors.append(f"{label} 必須為數值")
            elif not math.isfinite(v):
                errors.append(f"{label} 不可為 NaN 或無限大")
            elif not HARD_LIMITS[f][0] <= v <= HARD_LIMITS[f][1]:
                errors.append(f"{label} = {v:g} 超出合理範圍 [{HARD_LIMITS[f][0]:g}, {HARD_LIMITS[f][1]:g}] {FEATURE_UNITS[f]}")
            else:
                vec.append(float(v))
    if confirmed_label is not None and (isinstance(confirmed_label, bool) or confirmed_label not in (0, 1)
                                        or not isinstance(confirmed_label, int)):
        errors.append("confirmed_label 只能是 0（合規）、1（異常）或不提供")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)
    log.add(f"特徵 [電流 {vec[0]:g} A, 壓力 {vec[1]:g} MPa] 為合理範圍內的有限數值；"
            + ("未提供人工確認結果，本次不會更新模型。" if confirmed_label is None
               else f"人工確認結果：{confirmed_label}（{'異常' if confirmed_label else '合規'}）。"))

    # 2. 載入 / 訓練
    try:
        state, origin = load_state()
    except ValueError as e:
        log.add(f"感知器無法建立：{e}")
        return blocked("模型無法建立", "BLOCKED_BY_GUARDRAIL (model unavailable)", f"無法建立感知器：{e}")
    m = state["metrics"]
    log.add(("載入已存的感知器狀態" if origin == "loaded" else "依參考資料訓練感知器")
            + f"（資料：{state['source']}；學習率 η={state['eta']}）。訓練 {m['n_train']} 筆，"
            f"{m['epochs']} 個 epoch {'收斂（整輪零錯誤）' if m['converged'] else '未收斂'}，累計修正 {m['train_mistakes']} 次；"
            f"測試集準確率 {m['holdout_accuracy'] * 100:.1f}%；已累積人工更新 {state['n_updates']} 次。")

    # Guardrail 前置評估（結果在第 5 步呈現）
    z = [(vec[i] - state["mean"][i]) / state["std"][i] for i in range(2)]
    blocked_reasons, warnings = [], []
    if not m["converged"]:
        blocked_reasons.append("感知器訓練未收斂，資料可能不是線性可分")
    if m["holdout_accuracy"] < MIN_HOLDOUT_ACC:
        blocked_reasons.append(f"測試集準確率 {m['holdout_accuracy'] * 100:.1f}% < {MIN_HOLDOUT_ACC * 100:.0f}%，模型不可靠")
    for i, f in enumerate(FEATURES):
        lo, hi = state["ranges"][f]
        desc = f"{FEATURE_LABELS[f]}={vec[i]:g}{FEATURE_UNITS[f]}"
        if abs(z[i]) > BLOCK_Z:
            blocked_reasons.append(f"{desc} 的 |z|={abs(z[i]):.2f} > {BLOCK_Z:g}，遠離訓練資料範圍")
        elif vec[i] < lo or vec[i] > hi:
            warnings.append(f"{desc} 超出訓練資料範圍 [{lo:.1f}, {hi:.1f}]，判定屬外插，可信度下降")
        elif abs(z[i]) > WARN_Z:
            warnings.append(f"{desc} 的 |z|={abs(z[i]):.2f} > {WARN_Z:g}")
    if blocked_reasons:
        kind = "model quality" if (not m["converged"] or m["holdout_accuracy"] < MIN_HOLDOUT_ACC) else "extrapolation"
        return blocked("Guardrail 已攔截，不進行判定與更新", f"BLOCKED_BY_GUARDRAIL ({kind})",
                       "為避免誤導，已拒絕輸出合規判定：" + "；".join(blocked_reasons), blocked_reasons + warnings)

    # 3. 劃分
    w_before, b_before = list(state["w"]), state["b"]
    score = _score(state, z)
    norm = math.hypot(*state["w"])
    distance = score / norm if norm > 1e-12 else 0.0
    pred = 1 if score > 0 else 0
    log.add(f"z = [{z[0]:+.3f}, {z[1]:+.3f}]；score = w₁z₁ + w₂z₂ + b = {w_before[0]:+.3f}×{z[0]:+.3f} + {w_before[1]:+.3f}×{z[1]:+.3f} + {b_before:+.3f} = {score:+.4f}；"
            f"score > 0 → {pred}（{'異常' if pred else '合規'}）。距超平面 {abs(distance):.3f}（z 單位）。")

    # 4. 更新
    updated = False
    update_note = ""
    w_after, b_after = list(w_before), b_before
    if confirmed_label is None:
        update_note = "未提供人工確認結果，不更新權重。"
    elif confirmed_label == pred:
        update_note = "人工確認結果與預測一致（沒有分類錯誤），依感知器規則不更新權重。"
    elif state["n_updates"] >= MAX_UPDATES:
        update_note = f"預測與確認結果不符，但累計更新已達上限 {MAX_UPDATES} 次，不再更新（請先重設模型）。"
        warnings.append(update_note)
    else:
        delta = confirmed_label - pred
        w_after = [w_before[0] + state["eta"] * delta * z[0], w_before[1] + state["eta"] * delta * z[1]]
        b_after = b_before + state["eta"] * delta
        state["w"], state["b"] = w_after, b_after
        state["n_updates"] += 1
        state["update_log"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "features": vec, "predicted": pred,
            "confirmed": confirmed_label, "w_before": _weights_dict(w_before, b_before),
            "w_after": _weights_dict(w_after, b_after)})
        state["update_log"] = state["update_log"][-LOG_KEEP:]
        save_json(state, _state_path())
        updated = True
        update_note = (f"預測 {pred} ≠ 確認 {confirmed_label}，依 w ← w + η(y-ŷ)z 更新（η={state['eta']}，y-ŷ={delta:+d}）："
                       f"w₁ {w_before[0]:+.4f}→{w_after[0]:+.4f}，w₂ {w_before[1]:+.4f}→{w_after[1]:+.4f}，bias {b_before:+.4f}→{b_after:+.4f}。")
    after_score = w_after[0] * z[0] + w_after[1] * z[1] + b_after
    pred_after = 1 if after_score > 0 else 0
    if updated:
        update_note += f"更新後同一筆資料的判定為 {pred_after}（{'已修正' if pred_after == confirmed_label else '單次更新尚不足以修正，需更多確認樣本'}）。"
    log.add(update_note)

    # 5. Guardrail 結果
    if abs(distance) < NEAR_BOUNDARY:
        warnings.append(f"此筆資料非常接近決策邊界（距離 {abs(distance):.3f} < {NEAR_BOUNDARY}），判定不穩定，建議人工複核")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（測試集準確率 {m['holdout_accuracy'] * 100:.1f}% ≥ {MIN_HOLDOUT_ACC * 100:.0f}%、已收斂、輸入在可判定範圍內）。"
            + ("；".join(warnings) if warnings else ""))

    pts = state["plot_points"]
    xs = [p["x"] for p in pts] + [vec[0]]
    ys = [p["y"] for p in pts] + [vec[1]]
    x_lo, x_hi = min(xs) - 3, max(xs) + 3
    y_lo, y_hi = min(ys) - 0.2, max(ys) + 0.2
    status_label = "NON_COMPLIANT" if pred else "COMPLIANT"
    answer = ("判定為異常（NON_COMPLIANT）：目前電流與壓力的組合落在異常側，請確認量測值與設備狀態。" if pred
              else "判定為合規（COMPLIANT）：目前電流與壓力的組合落在合規側。")
    return finish({
        "status": "success", "found": True, "features": vec, "feature_names": FEATURES,
        "validation_result": pred, "status_label": status_label,
        "decision_score": round(score, 4), "distance_to_hyperplane": round(distance, 4),
        "z_scores": [round(v, 4) for v in z], "confirmed_label": confirmed_label,
        "weight_updated": updated, "update_note": update_note,
        "weights_before": _weights_dict(w_before, b_before),
        "updated_weights": _weights_dict(w_after, b_after),
        "result_after_update": pred_after, "eta": state["eta"], "n_updates": state["n_updates"],
        "update_log": state["update_log"][-10:], "data_source": state["source"],
        "model_metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()},
        "plot": {"points": pts, "line": _boundary_line(state, x_lo, x_hi, y_lo, y_hi),
                 "x_range": [round(x_lo, 2), round(x_hi, 2)], "y_range": [round(y_lo, 3), round(y_hi, 3)],
                 "point": {"x": vec[0], "y": vec[1], "label": pred}},
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_13_error_code_perceptron_check ===")
    res = check_error_code_perceptron([45.2, 2.1])
    res.pop("plot", None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
