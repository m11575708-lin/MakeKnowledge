"""
skill_24_preventive_maintenance_hierarchy.py - 設備風險凝聚階層式分群（建樹）技能

對應系統規格：US-15 / 13. 智慧生產指數預測與管理頁（呼叫順序：skill_24 → skill_25）
演算法機制：輸入防呆 -> 歐氏距離矩陣 -> 凝聚法逐步合併最近兩群（Lance–Williams 更新） -> 樹的品質檢查 -> Guardrail

說明：
  * 輸入是「風險方向一致的標準化指標矩陣」（每列一台設備；數值越大＝風險越高）。
    由呼叫端把 MTBF 取負號並做 z 分數（見 _equipment_data.risk_matrix）；未標準化時會警告，
    因為歐氏距離會被尺度大的指標（例如 MTBF 的數千小時）完全主導。
  * 群間距離（linkage）：single（最近鄰）、complete（最遠鄰）、average（平均，預設）。
  * 輸出 merge_history（scipy 慣例：[左節點, 右節點, 合併距離, 新群大小]）、leaf_order（畫樹狀圖的葉序）。
  * 共生相關係數（cophenetic correlation）衡量樹是否忠實保留原始距離；< 0.7 會警告。
  * 階層分群是確定性的（沒有隨機性），同一份資料與同一個 linkage 一定得到同一棵樹。
    但不同 linkage 會得到不同的樹，頁面可切換比較。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _hier as hier
    from ._spc_data import column_std_warnings, validate_matrix
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _hier as hier
    from _spc_data import column_std_warnings, validate_matrix

SKILL_NAME = "skill_24_preventive_maintenance_hierarchy"
MIN_ITEMS = 3
LOW_COPHENETIC = 0.70

PLAN = [
    ("設備風險矩陣與連結法防呆", "Boundary & Type Validation", "math"),
    ("計算歐氏距離矩陣", "Euclidean Distance Matrix  d(i,j)=√Σ(x_i−x_j)²", "math"),
    ("凝聚法逐步合併最近兩群", "Agglomerative Clustering (Lance–Williams update)", "Python Built-in"),
    ("樹的品質檢查（單調性與共生相關）", "Cophenetic Correlation & Monotonicity Check", "math"),
    ("階層樹 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def build_hierarchy(equipment_risk_matrix=None, linkage: str = "average", equipment_ids=None, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("hierarchy_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "linkage": linkage if isinstance(linkage, str) else None,
                       "merge_history": [], "leaf_order": [], "n_items": None, "cophenetic_correlation": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    errors = []
    X, errs = validate_matrix(equipment_risk_matrix, "equipment_risk_matrix", MIN_ITEMS)
    errors += errs
    if X is not None and len(X) > hier.MAX_ITEMS:
        errors.append(f"設備數 {len(X)} 超過上限 {hier.MAX_ITEMS}（純 Python 的 O(n³) 凝聚法效能限制）")
    if linkage not in hier.LINKAGES:
        errors.append(f"linkage 必須是 {'、'.join(hier.LINKAGES)} 之一")
    ids = None
    if X is not None and equipment_ids is not None:
        if not isinstance(equipment_ids, (list, tuple)) or len(equipment_ids) != len(X) or \
                any(not isinstance(i, str) or not i for i in equipment_ids):
            errors.append("equipment_ids 必須是與矩陣列數相同的非空字串陣列")
        elif len(set(equipment_ids)) != len(equipment_ids):
            errors.append("equipment_ids 不可重複")
        else:
            ids = list(equipment_ids)
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    n, dim = len(X), len(X[0])
    ids = ids or [f"#{i + 1}" for i in range(n)]
    log.add(f"{n} 台設備 × {dim} 項風險指標，連結法 {linkage}；矩陣為矩形且皆為有限數值。")

    # 2
    D0 = hier.distance_matrix(X)
    flat = [D0[i][j] for i in range(n) for j in range(i + 1, n)]
    dmin, dmax, dmean = min(flat), max(flat), sum(flat) / len(flat)
    if dmax <= 1e-12:
        log.add("所有設備的指標完全相同（距離皆為 0），無法建立階層。")
        return blocked("距離全為 0", "BLOCKED_BY_GUARDRAIL (identical items)", "所有設備指標完全相同，無法建立風險階層")
    log.add(f"計算 {len(flat)} 組設備對的歐氏距離：最小 {dmin:.3f}、平均 {dmean:.3f}、最大 {dmax:.3f}。")

    # 3
    tree = hier.agglomerate(X, linkage)
    merges = tree["merge_history"]
    first = merges[0]
    log.add(f"重複 {len(merges)} 次「找最近的兩群並合併」（{linkage} 連結）：第 1 次合併 {ids[first[0]] if first[0] < n else '節點' + str(first[0])} "
            f"與 {ids[first[1]] if first[1] < n else '節點' + str(first[1])}（距離 {first[2]:.3f}），"
            f"最後一次合併高度 {merges[-1][2]:.3f}（所有設備併成一群）。")

    # 4
    hs = [m[2] for m in merges]
    inversions = sum(1 for a, b in zip(hs, hs[1:]) if b < a - 1e-9)
    ccc = hier.cophenetic_correlation(D0, tree["cophenetic"])
    log.add(f"合併高度{'單調遞增（無倒退）' if inversions == 0 else f'出現 {inversions} 次倒退'}；"
            f"共生相關係數 = " + (f"{ccc:.3f}" if ccc is not None else "無法計算") + "（越接近 1 越忠實保留原始距離）。")

    # 5
    warnings = column_std_warnings(X)
    if ccc is not None and ccc < LOW_COPHENETIC:
        warnings.append(f"共生相關係數 {ccc:.2f} < {LOW_COPHENETIC}，這棵樹扭曲了原始距離，階層分群結果可信度低（可改用其他連結法）")
    if inversions:
        warnings.append(f"合併高度出現 {inversions} 次倒退，切割結果可能不直覺")
    ties = len(flat) - len({round(v, 9) for v in flat})
    if ties > 0.3 * len(flat):
        warnings.append("許多設備對距離相同（可能資料離散度太低），合併順序依編號決定，結果對微小變動敏感")
    guardrail = "PASSED_WITH_WARNINGS" if warnings else "PASSED"
    log.add(f"防呆檢核狀態：{guardrail}。" + ("；".join(warnings) if warnings else "矩陣已標準化、合併高度單調、共生相關係數足夠。"))

    return finish({
        "status": "success", "found": True, "linkage": linkage, "n_items": n, "n_indicators": dim,
        "equipment_ids": ids, "merge_history": [[m[0], m[1], round(m[2], 6), m[3]] for m in merges],
        "leaf_order": tree["leaf_order"], "cophenetic_correlation": round(ccc, 4) if ccc is not None else None,
        "monotonic": inversions == 0, "distance_stats": {"min": round(dmin, 4), "mean": round(dmean, 4), "max": round(dmax, 4)},
        "max_merge_height": round(merges[-1][2], 6), "suggested_threshold": round(hier.suggest_threshold(merges), 4) if hier.suggest_threshold(merges) is not None else None,
        "risk_matrix": [[round(v, 6) for v in row] for row in X],
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"{n} 台設備以 {linkage} 連結建立階層樹，最後合併高度 {merges[-1][2]:.2f}，共生相關係數 {ccc:.2f}。" if ccc is not None
        else f"{n} 台設備以 {linkage} 連結建立階層樹，最後合併高度 {merges[-1][2]:.2f}。",
    })


if __name__ == "__main__":
    try:
        from ._equipment_data import load_data, risk_matrix, INDICATORS
    except ImportError:
        from _equipment_data import load_data, risk_matrix, INDICATORS
    rows, _ = load_data()
    Z, _ = risk_matrix(rows, INDICATORS)
    r = build_hierarchy(Z, "average", [x["equipment_id"] for x in rows])
    print(json.dumps({k: v for k, v in r.items() if k != "steps"}, ensure_ascii=False, indent=2)[:1500])
