"""
skill_10_error_code_feature_matching.py - 故障碼物理特徵向量比對與權重校正技能

對應系統規格：US-06 / 08. 歷史維修案例檢索與備品推薦頁
演算法機制：故障碼格式防呆 -> 依故障碼分組歷史案例 -> 特徵中心與組內標準差
            -> 逆變異數權重校正 -> 高斯核親和度（信心度）-> Guardrail

校正權重：同一故障碼的案例中，某特徵越集中（相對離散度越小），越能代表該故障，權重越高。
        r_i = σ組內_i / σ全庫_i（無單位；σ組內設下限為 σ全庫 的 10%，避免權重爆衝），
        w_i ∝ 1 / r_i²，再正規化為平均 1。
信心度：conf = exp(-½ · mean(z_i²))，z_i = (x_i - 中心_i) / σ_i；這是核函數親和度，不是機率。
        z 為 0（與典型模式完全相同）時為 1。
"""

import json
import math
import re

try:
    from ._common import StepLog, default_output_path, save_json
    from ._repair_data import (ERROR_CODE_PATTERN, FEATURES, FEATURE_LABELS, FEATURE_UNITS,
                               clean_num, feature_stats, load_case_base, validate_vector)
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _repair_data import (ERROR_CODE_PATTERN, FEATURES, FEATURE_LABELS, FEATURE_UNITS,
                              clean_num, feature_stats, load_case_base, validate_vector)

SKILL_NAME = "skill_10_error_code_feature_matching"
MIN_CASES = 3
STD_FLOOR_RATIO = 0.10
LOW_CONFIDENCE = 0.05

PLAN = [
    ("故障碼格式與特徵向量防呆", "Regular Expression & Boundary Validation", "re, math"),
    ("依故障碼分組歷史案例", "Metadata Filtering (GroupBy error_code)", "json, os"),
    ("特徵中心與組內標準差", "Centroid & Sample Standard Deviation", "Python Built-in"),
    ("逆變異數權重校正", "Inverse-Variance Feature Weighting  w ∝ 1/σ²", "math"),
    ("高斯核信心度與 Guardrail 檢核", "Gaussian Kernel Affinity & Threshold-based Guardrail", "math, Python Control Flow"),
]


def match_error_code_pattern(error_code="E-8021", feature_vector=None, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("error_code_matching_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    echo_code = error_code if isinstance(error_code, str) else None
    echo_vec = ([clean_num(v) for v in feature_vector]
                if isinstance(feature_vector, (list, tuple)) else None)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None, extra=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "error_code": echo_code, "feature_vector": echo_vec,
                       "matched_pattern": None, "confidence": None, "feature_weights": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail,
                       "answer_text": message, **(extra or {})})

    # 1. 防呆
    errors = []
    code = error_code.strip().upper() if isinstance(error_code, str) else None
    if not code or not re.match(ERROR_CODE_PATTERN, code):
        errors.append(f"故障碼格式錯誤（收到 {error_code!r}），需為 E- 加 4 位數字，例如 E-8021")
    vec = None
    if feature_vector is not None:
        vec, vec_errors = validate_vector(feature_vector)
        errors += vec_errors
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)
    log.add(f"故障碼 {code} 格式正確"
            + (f"；特徵向量 {len(vec)} 維皆為合理範圍內的有限數值。" if vec else "；未提供特徵向量，僅輸出模式與校正權重。"))

    # 2. 分組
    base = load_case_base()
    all_cases = base["cases"]
    group = [c for c in all_cases if c["error_code"] == code]
    known = sorted({c["error_code"] for c in all_cases})
    log.add(f"自 {base['source']} 載入 {len(all_cases)} 筆案例；故障碼 {code} 共 {len(group)} 筆"
            f"（案例庫共 {len(known)} 種故障碼）。")
    if not group:
        return blocked("查無此故障碼的歷史案例", "BLOCKED_BY_GUARDRAIL (unknown error_code)",
                       f"案例庫中沒有故障碼 {code} 的紀錄。目前已收錄：{'、'.join(known)}。",
                       extra={"known_error_codes": known})

    # 3. 中心與標準差
    try:
        g_stats = feature_stats(all_cases)
    except ValueError as e:
        log.add(f"案例庫統計失敗：{e}")
        return blocked("案例庫統計失敗", "BLOCKED_BY_GUARDRAIL (degenerate case base)", str(e))
    n = len(group)
    centroid, within_std = [], []
    for i in range(len(FEATURES)):
        vals = [c["features"][i] for c in group]
        mean = sum(vals) / n
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
        centroid.append(mean)
        within_std.append(max(sd, STD_FLOOR_RATIO * g_stats[i]["std"]))
    log.add("組內特徵中心：" + "；".join(f"{FEATURE_LABELS[f]} {centroid[i]:.2f}{FEATURE_UNITS[f]}" for i, f in enumerate(FEATURES))
            + "；組內標準差（含下限）：" + "；".join(f"{within_std[i]:.3f}" for i in range(len(FEATURES))) + "。")

    # 4. 權重
    rel_std = [within_std[i] / g_stats[i]["std"] for i in range(len(FEATURES))]
    inv_var = [1.0 / (r * r) for r in rel_std]
    total = sum(inv_var)
    weights = [w * len(FEATURES) / total for w in inv_var]
    log.add("先把組內標準差除以全案例庫標準差（去除單位，避免 °C 與 MPa 的量級影響），得相對離散度："
            + "；".join(f"{FEATURE_LABELS[f]} {rel_std[i]:.3f}" for i, f in enumerate(FEATURES))
            + "。再取 w ∝ 1/相對離散度² 並正規化為平均 1："
            + "；".join(f"{FEATURE_LABELS[f]} {weights[i]:.3f}" for i, f in enumerate(FEATURES))
            + "。權重越高代表該特徵越能區辨此故障碼。")

    # 5. 信心度與 Guardrail
    pattern = max({c["pattern"] for c in group}, key=lambda p: sum(c["pattern"] == p for c in group))
    label = next(c["pattern_label"] for c in group if c["pattern"] == pattern)
    warnings = []
    if n < MIN_CASES:
        warnings.append(f"故障碼 {code} 僅有 {n} 筆歷史案例（< {MIN_CASES}），中心與權重不穩定")
    z_list, confidence = None, None
    if vec:
        z_list = [(vec[i] - centroid[i]) / within_std[i] for i in range(len(FEATURES))]
        confidence = math.exp(-0.5 * sum(z * z for z in z_list) / len(FEATURES))
        if confidence < LOW_CONFIDENCE:
            warnings.append(f"輸入特徵與 {code}（{label}）的典型模式差距很大（信心度 {confidence:.3f} < {LOW_CONFIDENCE}），"
                            "請確認故障碼是否選對")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}。"
            + (f"信心度 conf = exp(-½·mean(z²)) = {confidence:.3f}。" if confidence is not None else "未提供特徵向量，不計算信心度。")
            + ("；".join(warnings) if warnings else ""))

    answer = f"故障碼 {code} 對應模式為 {pattern}（{label}），共 {n} 筆歷史案例。"
    if confidence is not None:
        answer += f"目前特徵與該模式的吻合度（核親和度）為 {confidence:.2f}。"
    return finish({
        "status": "success", "found": True, "error_code": code, "feature_vector": echo_vec,
        "data_source": base["source"], "matched_pattern": pattern, "pattern_label": label,
        "confidence": round(confidence, 4) if confidence is not None else None, "n_cases": n,
        "centroid": [round(v, 4) for v in centroid], "within_std": [round(v, 4) for v in within_std],
        "feature_weights": [round(w, 4) for w in weights],
        "feature_weights_by_name": {f: round(weights[i], 4) for i, f in enumerate(FEATURES)},
        "z_scores": [round(z, 4) for z in z_list] if z_list else None,
        "known_error_codes": known, "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_10_error_code_feature_matching ===")
    print(json.dumps(match_error_code_pattern("E-8021", [2.8, 75.0, 1.8]), ensure_ascii=False, indent=2))
