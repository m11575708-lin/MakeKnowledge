"""
skill_11_spare_parts_recommendation.py - 維修備品推薦技能（物品協同過濾 Item-based CF）

對應系統規格：US-07 / 08. 歷史維修案例檢索與備品推薦頁
演算法機制：輸入防呆 -> 案例×備品領用矩陣 -> 備品間共現餘弦相似度
            -> 以近鄰案例加權的使用輪廓計算推薦分數 -> 庫存與支持度 Guardrail

備品相似度：sim(i,j) = co(i,j) / √(n_i · n_j)，co 為同時被同一工單領用的次數，n 為各自被領用的工單數。
使用輪廓：profile_i = Σ_近鄰案例 (相似度 × 該案例是否領用備品 i)。
推薦分數：score_j = Σ_i profile_i · sim(i,j) / Σ_i profile_i，範圍 0~1；
          j 本身被近鄰直接領用時 sim(j,j)=1，所以「近鄰常用的備品」與「常和它們一起用的備品」都會得分。
庫存標籤：OUT 缺料、LOW 庫存不高於安全庫存、NORMAL 正常。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._repair_data import load_case_base, stock_status
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _repair_data import load_case_base, stock_status

SKILL_NAME = "skill_11_spare_parts_recommendation"
MIN_SCORE = 0.10
MAX_TOP_N = 15

PLAN = [
    ("案例編號與近鄰權重防呆", "Boundary & Type Validation", "math"),
    ("建立案例×備品領用矩陣", "Case-Part Usage Matrix", "json, Python Built-in"),
    ("計算備品間共現餘弦相似度", "Item-based CF: Co-occurrence Cosine Similarity", "math"),
    ("近鄰加權推薦分數計算", "Weighted Item-based Collaborative Filtering", "Python Built-in Sorting"),
    ("庫存與支持度 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def recommend_spare_parts(case_id=None, neighbors=None, top_n=5, min_score=MIN_SCORE,
                          output_json_path: str = None) -> dict:
    """
    case_id：單一歷史案例（權重 1）。
    neighbors：[{"case_id": ..., "similarity": 0~1}, ...]，優先於 case_id（通常來自 skill_09 的 Top-K）。
    """
    out_path = output_json_path or default_output_path("spare_parts_recommendation_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(reason_label: str, guardrail: str, message: str, warnings=None) -> dict:
        log.skip_to_last(reason_label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "recommended_parts": [], "seed_cases": [],
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1. 防呆
    errors, seeds = [], []
    if neighbors is not None:
        if not isinstance(neighbors, (list, tuple)) or not neighbors:
            errors.append("neighbors 必須是非空陣列")
        else:
            for item in neighbors:
                cid = item.get("case_id") if isinstance(item, dict) else None
                sim = item.get("similarity", 1.0) if isinstance(item, dict) else None
                if not isinstance(cid, str) or not cid:
                    errors.append("neighbors 的每一筆都需要 case_id 字串")
                elif isinstance(sim, bool) or not isinstance(sim, (int, float)) or not math.isfinite(sim) or not 0 < sim <= 1:
                    errors.append(f"案例 {cid} 的 similarity 必須是大於 0、不超過 1 的數值")
                else:
                    seeds.append((cid, float(sim)))
    elif isinstance(case_id, str) and case_id.strip():
        seeds = [(case_id.strip(), 1.0)]
    else:
        errors.append("請提供 case_id，或由 skill_09 檢索到的 neighbors（前一步可能被 Guardrail 攔截）")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= MAX_TOP_N:
        errors.append(f"top_n 必須是 1 到 {MAX_TOP_N} 的整數")
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)) or not math.isfinite(min_score) or not 0 <= min_score < 1:
        errors.append("min_score 必須介於 0 到 1（不含 1）")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)",
                       "輸入未通過驗證：" + "；".join(errors), errors)

    base = load_case_base()
    by_id = {c["case_id"]: c for c in base["cases"]}
    unknown = [cid for cid, _ in seeds if cid not in by_id]
    if unknown:
        log.add(f"案例庫查無案例：{'、'.join(unknown)}。")
        return blocked("案例不存在", "BLOCKED_BY_GUARDRAIL (unknown case_id)",
                       f"案例庫中找不到案例：{'、'.join(unknown)}。")
    log.add(f"近鄰案例 {len(seeds)} 筆：" + "、".join(f"{cid}(權重 {s:.2f})" for cid, s in seeds) + "；top_n 與最低分數門檻皆合理。")

    # 2. 領用矩陣
    part_ids = sorted({p for c in base["cases"] for p in c["parts_used"]})
    usage = {p: {c["case_id"] for c in base["cases"] if p in c["parts_used"]} for p in part_ids}
    n_used = {p: len(usage[p]) for p in part_ids}
    log.add(f"自 {base['source']} 建立 {len(base['cases'])} 筆案例 × {len(part_ids)} 種備品的 0/1 領用矩陣；"
            f"領用次數最多的備品：{max(n_used, key=n_used.get)}（{max(n_used.values())} 次）。")

    # 3. 共現餘弦
    def sim(i, j):
        if i == j:
            return 1.0
        co = len(usage[i] & usage[j])
        return co / math.sqrt(n_used[i] * n_used[j]) if co else 0.0
    log.add("sim(i,j) = 共現次數 / √(nᵢ·nⱼ)，對所有備品配對計算（對角線為 1）。")

    # 4. 推薦分數
    profile = {p: 0.0 for p in part_ids}
    for cid, w in seeds:
        for p in by_id[cid]["parts_used"]:
            profile[p] += w
    total = sum(profile.values())
    seed_parts = [p for p in part_ids if profile[p] > 0]
    catalog = {p["part_id"]: p for p in base["parts"]}
    scores = {}
    if total > 0:
        for j in part_ids:
            scores[j] = sum(profile[i] * sim(i, j) for i in seed_parts) / total
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    log.add(f"近鄰案例共領用 {len(seed_parts)} 種備品，使用輪廓加總 {total:.2f}；"
            "score_j = Σ profile_i·sim(i,j) / Σ profile_i；最高分："
            + "、".join(f"{p}({s:.2f})" for p, s in ranked[:3]) + "。")

    # 5. Guardrail
    warnings = []
    if total <= 0:
        guardrail = "BLOCKED_BY_GUARDRAIL (no parts in neighbors)"
        log.add(f"防呆檢核狀態：{guardrail}。近鄰案例都沒有備品領用紀錄。")
        return finish({"status": "success", "found": False, "recommended_parts": [],
                       "seed_cases": [{"case_id": c, "weight": s} for c, s in seeds],
                       "warnings": ["近鄰案例沒有備品領用紀錄"], "guardrail_status": guardrail,
                       "answer_text": "近鄰案例都沒有備品領用紀錄，無法推薦備品。"})
    recs = []
    for p, s in ranked:
        if s < min_score or len(recs) >= top_n:
            continue
        meta = catalog.get(p, {"name": "（備品主檔無此料號）", "stock": 0, "safety_stock": 0})
        status = stock_status(meta) if p in catalog else "UNKNOWN"
        recs.append({
            "part_id": p, "name": meta["name"], "score": round(s, 4),
            "source": "近鄰直接領用" if profile[p] > 0 else "共現推薦",
            "used_in_neighbors": sum(1 for cid, _ in seeds if p in by_id[cid]["parts_used"]),
            "support_cases": n_used[p], "stock": meta["stock"], "safety_stock": meta["safety_stock"],
            "stock_status": status,
        })
    if not recs:
        guardrail = f"BLOCKED_BY_GUARDRAIL (all scores < {min_score:g})"
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "recommended_parts": [],
                       "seed_cases": [{"case_id": c, "weight": s} for c, s in seeds],
                       "warnings": ["沒有備品達到最低推薦分數"], "guardrail_status": guardrail,
                       "answer_text": f"沒有備品的推薦分數達到門檻 {min_score:g}。"})
    low_support = [r["part_id"] for r in recs if r["support_cases"] < 2]
    if low_support:
        warnings.append("以下備品只在 1 張工單出現過，推薦依據薄弱：" + "、".join(low_support))
    out_parts = [r for r in recs if r["stock_status"] == "OUT"]
    low_parts = [r for r in recs if r["stock_status"] == "LOW"]
    unknown_parts = [r["part_id"] for r in recs if r["stock_status"] == "UNKNOWN"]
    if out_parts:
        warnings.append("缺料：" + "、".join(f"{r['part_id']} {r['name']}" for r in out_parts) + "，請先確認調撥或採購")
    if low_parts:
        warnings.append("庫存偏低：" + "、".join(f"{r['part_id']} {r['name']}（{r['stock']}/{r['safety_stock']}）" for r in low_parts))
    if unknown_parts:
        warnings.append("備品主檔缺少料號：" + "、".join(unknown_parts))
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}。推薦 {len(recs)} 項（分數 ≥ {min_score:g}）；缺料 {len(out_parts)} 項、庫存偏低 {len(low_parts)} 項。")

    top = recs[0]
    answer = f"建議備品 {len(recs)} 項，首選 {top['part_id']} {top['name']}（推薦分數 {top['score']:.2f}）。"
    if out_parts:
        answer += f"其中 {len(out_parts)} 項目前缺料。"
    return finish({
        "status": "success", "found": True, "data_source": base["source"],
        "seed_cases": [{"case_id": c, "weight": round(s, 4)} for c, s in seeds],
        "recommended_parts": recs, "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_11_spare_parts_recommendation ===")
    print(json.dumps(recommend_spare_parts(case_id="MA-2024-089"), ensure_ascii=False, indent=2))
