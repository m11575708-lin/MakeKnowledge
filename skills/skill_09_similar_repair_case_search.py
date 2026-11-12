"""
skill_09_similar_repair_case_search.py - 相似維修案例 KNN 檢索技能

對應系統規格：US-06 / 08. 歷史維修案例檢索與備品推薦頁
演算法機制：輸入防呆 -> 案例庫載入與 Z-Score 標準化 -> 加權歐氏距離
            -> KNN Top-K 排序 -> 相似度門檻 Guardrail

距離：d = sqrt( mean_i( w_i · (z_query_i - z_case_i)² ) )，z 以「整個案例庫」的平均與標準差標準化，
      使振動(mm/s)、溫度(°C)、壓力(MPa) 的量級可以相比；w 為特徵權重（平均 1，可由 skill_10 校正）。
相似度：similarity = 1 / (1 + d)，d=0 時為 1，距離越大越接近 0。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._repair_data import (FEATURES, FEATURE_LABELS, FEATURE_UNITS, clean_num, feature_stats,
                               load_case_base, validate_vector, validate_weights)
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _repair_data import (FEATURES, FEATURE_LABELS, FEATURE_UNITS, clean_num, feature_stats,
                              load_case_base, validate_vector, validate_weights)

SKILL_NAME = "skill_09_similar_repair_case_search"
MAX_TOP_K = 10

PLAN = [
    ("特徵向量、K 值與權重防呆", "Boundary & Type Validation", "math"),
    ("載入案例庫並 Z-Score 標準化", "Z-Score Standardization", "json, math"),
    ("加權歐氏距離計算", "Weighted Euclidean Distance", "math"),
    ("KNN Top-K 近鄰排序擷取", "K-Nearest Neighbors (KNN)", "Python Built-in Sorting"),
    ("相似度門檻 Guardrail 檢核與結果生成", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def search_similar_repair_cases(
    feature_vector=None, top_k=3, weights=None, error_code=None,
    restrict_to_error_code=False, min_similarity=0.30, output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("similar_repair_cases_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    echo_vec = ([clean_num(v) for v in feature_vector] if isinstance(feature_vector, (list, tuple)) else None)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "feature_vector": echo_vec,
                       "top3_similar_cases": [], "warnings": warnings or [message],
                       "guardrail_status": guardrail, "answer_text": message})

    # 1. 防呆
    errors = []
    vec, vec_errors = validate_vector(feature_vector) if feature_vector is not None else (None, ["缺少 feature_vector"])
    errors += vec_errors
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
        errors.append(f"top_k 必須是 1 到 {MAX_TOP_K} 的整數")
    w, w_errors = validate_weights(weights)
    errors += w_errors
    if (isinstance(min_similarity, bool) or not isinstance(min_similarity, (int, float))
            or not math.isfinite(min_similarity) or not 0.0 <= min_similarity < 1.0):
        errors.append("min_similarity 必須介於 0 到 1（不含 1）")
    code = error_code.strip().upper() if isinstance(error_code, str) and error_code.strip() else None
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)
    log.add(f"特徵向量 {len(vec)} 維皆為合理範圍內的有限數值；K={top_k}；"
            f"權重（平均 1）：{[round(x, 3) for x in w]}；最低相似度門檻 {min_similarity:g}。")

    # 2. 載入與標準化
    base = load_case_base()
    cases = base["cases"]
    try:
        stats = feature_stats(cases)
    except ValueError as e:
        log.add(f"案例庫統計失敗：{e}")
        return blocked("案例庫統計失敗", "BLOCKED_BY_GUARDRAIL (degenerate case base)", str(e))
    candidates = [c for c in cases if c["error_code"] == code] if (restrict_to_error_code and code) else cases
    if not candidates:
        log.add(f"限定故障碼 {code} 後沒有候選案例。")
        return blocked("無候選案例", "BLOCKED_BY_GUARDRAIL (no candidates)",
                       f"案例庫中沒有故障碼 {code} 的歷史案例，無法限定比對。可取消「僅比對相同故障碼」再試。")
    zq = [(vec[i] - stats[i]["mean"]) / stats[i]["std"] for i in range(len(FEATURES))]
    log.add(f"自 {base['source']} 載入 {len(cases)} 筆案例，以全案例庫的 μ、σ 標準化；"
            f"候選 {len(candidates)} 筆" + (f"（限定故障碼 {code}）" if restrict_to_error_code and code else "")
            + "。查詢向量 z：" + "；".join(f"{FEATURES[i]}={zq[i]:+.2f}" for i in range(len(FEATURES))) + "。")

    # 3. 距離
    scored = []
    for c in candidates:
        zc = [(c["features"][i] - stats[i]["mean"]) / stats[i]["std"] for i in range(len(FEATURES))]
        d = math.sqrt(sum(w[i] * (zq[i] - zc[i]) ** 2 for i in range(len(FEATURES))) / len(FEATURES))
        scored.append((d, c, zc))
    log.add("對每筆候選案例計算 d = √(mean(wᵢ·(z查詢ᵢ − z案例ᵢ)²))，並換算 similarity = 1/(1+d)。")

    # 4. KNN
    scored.sort(key=lambda t: (t[0], t[1]["case_id"]))
    k = min(top_k, len(scored))
    top = scored[:k]
    log.add(f"依距離升冪排序，取 Top-{k}：" + "、".join(f"{c['case_id']}(d={d:.3f})" for d, c, _ in top) + "。")

    # 5. Guardrail
    warnings = []
    if k < top_k:
        warnings.append(f"候選案例只有 {len(scored)} 筆，少於要求的 K={top_k}")
    out_of_range = [FEATURE_LABELS[f] for i, f in enumerate(FEATURES)
                    if vec[i] < stats[i]["min"] or vec[i] > stats[i]["max"]]
    if out_of_range:
        warnings.append("以下參數超出案例庫範圍，檢索結果的參考性下降：" + "、".join(out_of_range))
    results = []
    for rank, (d, c, zc) in enumerate(top, 1):
        results.append({
            "rank": rank, "case_id": c["case_id"], "similarity": round(1.0 / (1.0 + d), 4), "distance": round(d, 4),
            "error_code": c["error_code"], "pattern": c["pattern"], "pattern_label": c["pattern_label"],
            "equipment_id": c["equipment_id"], "date": c["date"], "description": c["description"],
            "steps": c["steps"], "parts_used": c["parts_used"], "features": c["features"],
            "feature_diff": [{"feature": f, "label": FEATURE_LABELS[f], "unit": FEATURE_UNITS[f],
                              "query": vec[i], "case": c["features"][i], "z_diff": round(zq[i] - zc[i], 3)}
                             for i, f in enumerate(FEATURES)],
            "code_match": bool(code and c["error_code"] == code),
        })
    best = results[0]
    base_result = {"status": "success", "feature_vector": vec, "error_code": code, "top_k": k,
                   "data_source": base["source"], "weights": [round(x, 4) for x in w],
                   "min_similarity": min_similarity, "restricted_to_error_code": bool(restrict_to_error_code and code),
                   "n_candidates": len(candidates)}
    if best["similarity"] < min_similarity:
        guardrail = f"BLOCKED_BY_GUARDRAIL (Best similarity {best['similarity']:.4f} < Threshold {min_similarity:g})"
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({**base_result, "found": False, "top3_similar_cases": [], "best_similarity": best["similarity"],
                       "warnings": warnings, "guardrail_status": guardrail,
                       "answer_text": "案例庫中沒有足夠相似的歷史案例（最高相似度 "
                                      f"{best['similarity']:.2f} < 門檻 {min_similarity:g}），不提供勉強的比對結果。"})
    guardrail = ("PASSED" if not warnings else "PASSED_WITH_WARNINGS") + f" (Best {best['similarity']:.4f} >= {min_similarity:g})"
    log.add(f"防呆檢核狀態：{guardrail}。" + ("；".join(warnings) if warnings else "查詢參數皆在案例庫範圍內。"))
    return finish({**base_result, "found": True, "top3_similar_cases": results, "best_similarity": best["similarity"],
                   "warnings": warnings, "guardrail_status": guardrail,
                   "answer_text": f"找到 {k} 筆相似歷史案例，最相似為 {best['case_id']}（{best['equipment_id']}，"
                                  f"{best['pattern_label']}，相似度 {best['similarity']:.2f}）。"})


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_09_similar_repair_case_search ===")
    res = search_similar_repair_cases([2.8, 75.0, 1.8], 3)
    for r in res.get("top3_similar_cases", []):
        r.pop("steps", None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
