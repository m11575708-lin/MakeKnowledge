"""
skill_25_factory_risk_dendrogram_eval.py - 樹狀圖切割、風險階層評估與預防維護排程技能

對應系統規格：US-15 / 13. 智慧生產指數預測與管理頁（呼叫順序：skill_24 → skill_25）
演算法機制：輸入與樹驗證 -> 依距離門檻切樹 -> 各群風險分數與分級 -> 預防維護排程 -> 切割可信度 Guardrail 與風險摘要

說明：
  * 切樹：合併距離 ≤ 門檻的合併全部採用，其餘不合併；剩下的連通群就是風險階層。
    不需事先指定群數，門檻越小群越多。未提供門檻時使用「最後 8 次合併中最大高度落差的中點」。
  * 群風險分數 = 群內設備「風險方向 z 分數」的平均（跨指標再平均）。分級（高／中／低）是這批設備之間的「相對」排名，
    不是絕對的危險程度：全部設備都很健康時，排最前面的群依然會被標成「高風險」。
  * 排程是我定義的簡單規則（規格只給「action_week」概念）：
    設備依「群風險高到低、群內個別風險高到低」排序，每週最多保養 capacity_per_week 台，
    第 k 台排在第 ⌈k/capacity⌉ 週；單一班組、不考慮停機窗口、備品與人力限制。實際排程需由主管依現場條件調整。
  * 切割品質：平均輪廓係數（在風險矩陣上用歐氏距離）與門檻距離最近合併高度的相對距離（切割穩健度）。
  * 風險摘要只陳述資料裡算得出來的事實（群大小、區域集中度、各指標平均），不編造原因。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _hier as hier
    from . import _kmeans as km
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _hier as hier
    import _kmeans as km

SKILL_NAME = "skill_25_factory_risk_dendrogram_eval"
CAPACITY_RANGE = (1, 20)
TOO_MANY_CLUSTERS = 8
LOW_SILHOUETTE = 0.25
FRAGILE_GAP = 0.05          # 門檻與最近合併高度相差 < 最大高度的 5% → 切割不穩健
ZONE_CONCENTRATION = 0.6

PLAN = [
    ("輸入與階層樹驗證", "Boundary & Type Validation (threshold, tree integrity)", "math"),
    ("依距離門檻切割樹", "Dendrogram Cut at Distance Threshold (merge height ≤ threshold)", "Python Built-in"),
    ("計算各群風險分數與分級", "Mean Risk Score & Relative Ranking", "math"),
    ("建立預防維護排程", "Priority Scheduling (risk desc, weekly capacity)", "Python Built-in"),
    ("切割可信度 Guardrail 與風險摘要", "Silhouette & Cut-robustness Guardrail", "math"),
]


def _nested(merges, n, ids):
    nodes = {}
    for i in range(n):
        nodes[i] = {"node_id": i, "label": ids[i], "height": 0.0, "size": 1}
    for s, (a, b, d, size) in enumerate(merges):
        nodes[n + s] = {"node_id": n + s, "height": d, "size": size, "children": [nodes[a], nodes[b]]}
    return nodes[n + len(merges) - 1] if merges else nodes[0]


def _valid_hierarchy(h):
    if not isinstance(h, dict) or not h.get("found"):
        return "階層樹不存在或 skill_24 已被安全檢核攔截"
    mh, ids, X = h.get("merge_history"), h.get("equipment_ids"), h.get("risk_matrix")
    if not isinstance(ids, list) or not ids or not isinstance(mh, list) or len(mh) != len(ids) - 1:
        return "階層樹結構不完整（merge_history 長度需為設備數 − 1）"
    if not isinstance(X, list) or len(X) != len(ids):
        return "階層樹缺少 risk_matrix"
    n = len(ids)
    for s, m in enumerate(mh):
        if not isinstance(m, (list, tuple)) or len(m) != 4 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in m):
            return f"merge_history 第 {s + 1} 筆格式錯誤"
        if not (0 <= m[0] < n + s and 0 <= m[1] < n + s) or m[0] == m[1]:
            return f"merge_history 第 {s + 1} 筆參照了不存在的節點"
        if m[2] < 0:
            return f"merge_history 第 {s + 1} 筆距離為負"
    return None


def evaluate_dendrogram(distance_threshold=None, hierarchy=None, equipment_rows=None, capacity_per_week: int = 3,
                        start_week: int = 1, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("dendrogram_eval_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "clusters_count": None, "dendrogram_tree": None,
                       "preventive_schedule": [], "risk_summary": None, "groups": [],
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    errors = []
    if hierarchy is None:        # 規格輸入只有 distance_threshold：自動以示範設備資料建樹
        try:
            from .skill_24_preventive_maintenance_hierarchy import build_hierarchy
            from ._equipment_data import INDICATORS, load_data, risk_matrix
        except ImportError:
            from skill_24_preventive_maintenance_hierarchy import build_hierarchy
            from _equipment_data import INDICATORS, load_data, risk_matrix
        rows, _ = load_data()
        Z, _ = risk_matrix(rows, INDICATORS)
        hierarchy = build_hierarchy(Z, "average", [r["equipment_id"] for r in rows])
        equipment_rows = equipment_rows or rows
    herr = _valid_hierarchy(hierarchy)
    if herr:
        errors.append(herr)
    thr = None
    if distance_threshold is None and not herr:
        thr = hierarchy.get("suggested_threshold")
        if thr is None:
            errors.append("無法自動建議門檻，請提供 distance_threshold")
    elif distance_threshold is not None:
        if isinstance(distance_threshold, bool) or not isinstance(distance_threshold, (int, float)) or not math.isfinite(distance_threshold) or distance_threshold <= 0:
            errors.append("distance_threshold 必須是大於 0 的有限數值")
        else:
            thr = float(distance_threshold)
    if isinstance(capacity_per_week, bool) or not isinstance(capacity_per_week, int) or not CAPACITY_RANGE[0] <= capacity_per_week <= CAPACITY_RANGE[1]:
        errors.append(f"capacity_per_week 需為 {CAPACITY_RANGE[0]}–{CAPACITY_RANGE[1]} 的整數")
    if isinstance(start_week, bool) or not isinstance(start_week, int) or not 1 <= start_week <= 52:
        errors.append("start_week 需為 1–52 的整數")
    raw_by_id = None
    if equipment_rows is not None and not herr:
        if not isinstance(equipment_rows, list) or any(not isinstance(r, dict) or "equipment_id" not in r for r in equipment_rows):
            errors.append("equipment_rows 必須是含 equipment_id 的物件陣列")
        else:
            raw_by_id = {r["equipment_id"]: r for r in equipment_rows}
            missing = [i for i in hierarchy["equipment_ids"] if i not in raw_by_id]
            if missing:
                errors.append(f"equipment_rows 缺少設備：{'、'.join(missing[:5])}")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    ids, merges, X = hierarchy["equipment_ids"], hierarchy["merge_history"], hierarchy["risk_matrix"]
    n = len(ids)
    auto = distance_threshold is None
    log.add(f"階層樹含 {n} 台設備、{len(merges)} 次合併（最大高度 {merges[-1][2]:.3f}）；"
            f"距離門檻 {thr:.3f}{'（未指定，取最後幾次合併最大高度落差的中點）' if auto else ''}；每週保養上限 {capacity_per_week} 台。")

    # 2
    raw_labels = hier.cut_tree(merges, n, thr)
    k = max(raw_labels) + 1
    used = sum(1 for m in merges if m[2] <= thr + 1e-12)
    log.add(f"採用合併距離 ≤ {thr:.3f} 的 {used} 次合併（共 {len(merges)} 次），其餘 {len(merges) - used} 次不合併 → 切成 {k} 個風險階層。")

    # 3
    members = {g: [i for i in range(n) if raw_labels[i] == g] for g in range(k)}
    item_score = [sum(row) / len(row) for row in X]
    gscore = {g: sum(item_score[i] for i in idx) / len(idx) for g, idx in members.items()}
    order = sorted(range(k), key=lambda g: (-gscore[g], min(members[g])))
    rank_of = {g: r + 1 for r, g in enumerate(order)}            # 1 = 風險最高
    labels = [rank_of[raw_labels[i]] for i in range(n)]

    def tier(r):
        if k == 1:
            return "未分層"
        if r == 1:
            return "高風險"
        if r == k:
            return "低風險"
        return "中風險"

    groups = []
    for g in order:
        idx = sorted(members[g], key=lambda i: -item_score[i])
        zones = {}
        mean_ind = None
        if raw_by_id:
            for i in idx:
                z = raw_by_id[ids[i]].get("zone")
                if z:
                    zones[z] = zones.get(z, 0) + 1
            keys = [c for c in ("failure_rate", "mtbf_hours", "load_pct") if all(isinstance(raw_by_id[ids[i]].get(c), (int, float)) for i in idx)]
            mean_ind = {c: round(sum(raw_by_id[ids[i]][c] for i in idx) / len(idx), 3) for c in keys}
        groups.append({"group": rank_of[g], "tier": tier(rank_of[g]), "size": len(idx), "risk_score": round(gscore[g], 4),
                       "members": [ids[i] for i in idx], "member_scores": [round(item_score[i], 4) for i in idx],
                       "zones": zones, "mean_indicators": mean_ind})
    log.add("群風險分數 = 群內各設備「風險方向 z 分數」跨指標平均後再取群平均；由高到低排序並標示相對風險層級：" +
            "；".join(f"群{x['group']}（{x['tier']}）{x['size']} 台、分數 {x['risk_score']:+.2f}" for x in groups) + "。")

    # 4
    seq = []
    for gi in groups:
        for mid, sc in zip(gi["members"], gi["member_scores"]):
            seq.append((gi["group"], mid))
    week_of = {}
    for pos, (_, mid) in enumerate(seq):
        week_of[mid] = start_week + pos // capacity_per_week
    schedule = []
    for gi in groups:
        weeks = [week_of[m] for m in gi["members"]]
        gi["action_week"], gi["end_week"] = min(weeks), max(weeks)
        schedule.append({"group": gi["group"], "tier": gi["tier"], "action_week": min(weeks), "end_week": max(weeks),
                         "machines": [{"equipment_id": m, "week": week_of[m]} for m in gi["members"]]})
    total_weeks = max(week_of.values()) - start_week + 1
    log.add(f"排程：設備依「群風險高→低、群內風險高→低」排序，每週最多 {capacity_per_week} 台，自第 {start_week} 週起共需 {total_weeks} 週；"
            + "；".join(f"群{s['group']}：第 {s['action_week']}–{s['end_week']} 週" for s in schedule) + "。")

    # 5
    warnings = []
    sil = km.silhouette(X, raw_labels, k) if 2 <= k <= n - 1 else None
    hs = [m[2] for m in merges]
    below = max([h for h in hs if h <= thr + 1e-12], default=None)
    above = min([h for h in hs if h > thr + 1e-12], default=None)
    near = min([abs(thr - h) for h in hs])
    if k == 1:
        warnings.append(f"門檻 {thr:.2f} ≥ 最大合併高度 {hs[-1]:.2f}，所有設備併成同一群，無法區分維護優先順序；請調小門檻")
    elif k == n:
        warnings.append(f"門檻 {thr:.2f} 小於最小合併高度 {hs[0]:.2f}，每台設備自成一群，沒有做到分層；請調大門檻")
    elif k > TOO_MANY_CLUSTERS:
        warnings.append(f"切成 {k} 群（> {TOO_MANY_CLUSTERS}），階層太細，不利於排定保養視窗")
    if 2 <= k < n:
        if near < FRAGILE_GAP * hs[-1]:
            warnings.append(f"門檻 {thr:.2f} 非常接近一個合併高度（相差 {near:.3f}），微調門檻就會改變分群，切割不穩健")
        if sil is not None and sil < LOW_SILHOUETTE:
            warnings.append(f"平均輪廓係數 {sil:.2f} < {LOW_SILHOUETTE}，群與群的界線不明顯")
        single = [g["members"][0] for g in groups if g["size"] == 1]
        if single:
            warnings.append(f"{len(single)} 台設備自成一群（{'、'.join(single[:4])}{'…' if len(single) > 4 else ''}），可能是離群設備，建議個別檢視")
    if k >= 2:
        warnings.append("風險層級是這批設備之間的相對排名，不是絕對的危險程度")
    warnings.append("排程為單一班組、依風險排序的簡化規則，未考慮停機窗口、備品與人力，需由主管調整")
    guardrail = "PASSED_WITH_WARNINGS" if warnings else "PASSED"

    # 風險摘要（只陳述算得出來的事實）
    summary = "切成單一群，無法比較風險。"
    if k >= 2:
        top = groups[0]
        parts = [f"高風險群含 {top['size']} 台（{'、'.join(top['members'][:6])}{'…' if top['size'] > 6 else ''}）"]
        if top["zones"]:
            z, c = max(top["zones"].items(), key=lambda kv: kv[1])
            if top["size"] >= 3 and c / top["size"] >= ZONE_CONCENTRATION:
                parts.append(f"其中 {c}/{top['size']} 台位於{z}")
        mi = top.get("mean_indicators")
        if mi:
            parts.append("群平均 " + "、".join(
                f"{ {'failure_rate': '故障率', 'mtbf_hours': 'MTBF', 'load_pct': '負載'}[c] } {v:g}" for c, v in mi.items()))
        summary = "；".join(parts) + f"。建議先從第 {top['action_week']} 週開始保養。"
    log.add(f"切割評估：平均輪廓係數 " + (f"{sil:.3f}" if sil is not None else "不適用") + f"；門檻下方最近的合併高度 "
            + (f"{below:.3f}" if below is not None else "無") + "、上方 " + (f"{above:.3f}" if above is not None else "無")
            + f"。防呆檢核狀態：{guardrail}。" + ("；".join(warnings[:2])))

    return finish({
        "status": "success", "found": True, "clusters_count": k, "threshold_used": round(thr, 6), "threshold_auto": auto,
        "labels": labels, "groups": groups, "dendrogram_tree": _nested(merges, n, ids),
        "preventive_schedule": schedule, "weeks_total": total_weeks, "capacity_per_week": capacity_per_week, "start_week": start_week,
        "risk_summary": summary, "silhouette": round(sil, 4) if sil is not None else None,
        "threshold_gap": {"below": below, "above": above}, "max_merge_height": hs[-1],
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"切成 {k} 個風險階層，" + (f"高風險群 {groups[0]['size']} 台，" if k >= 2 else "") + f"預防維護共 {total_weeks} 週。",
    })


if __name__ == "__main__":
    r = evaluate_dendrogram()
    print(json.dumps({k: v for k, v in r.items() if k not in ("steps", "dendrogram_tree")}, ensure_ascii=False, indent=2)[:2500])
