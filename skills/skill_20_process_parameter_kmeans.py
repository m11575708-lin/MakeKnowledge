"""
skill_20_process_parameter_kmeans.py - 製程參數 K-Means 分群技能

對應系統規格：US-12 / 12. 製程參數分群與 SPC 管制監控頁（呼叫順序：skill_21 → skill_20 → skill_22）
演算法機制：輸入防呆 -> k-means++ 初始化（多起點） -> Lloyd 迭代（指派 + 更新 μ_k = 群內平均）
            -> SSE／群大小／變異解釋率／輪廓係數 -> Guardrail

說明：
  * K 由 skill_21 的手肘法建議，或由使用者指定。
  * 為了讓群編號穩定，群會依「中心的第一個座標」由小到大重新編號。
  * 輸入應為 z 分數；中心座標也是 z 分數（換回原始單位由呼叫端用平均與標準差處理）。
  * K-Means 假設群接近球形、大小相近；對離群點敏感（離群點會拉動中心或自成小群，會警告）。
"""

import json

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _kmeans as km
    from ._spc_data import column_std_warnings, validate_matrix
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _kmeans as km
    from _spc_data import column_std_warnings, validate_matrix

SKILL_NAME = "skill_20_process_parameter_kmeans"
K_LIMIT = 10
N_INIT = 10
SEED = 42
MAX_ITER = 100
TINY_CLUSTER = 0.03         # 群大小低於全體 3% 視為極小群
LOW_SILHOUETTE = 0.25       # < 0.25：沒有實質群結構
WEAK_SILHOUETTE = 0.50      # 0.25–0.5：結構薄弱；≥0.5 才算有合理結構（實測無結構資料最高約 0.34–0.42）

PLAN = [
    ("輸入資料與群數 K 防呆", "Boundary & Type Validation", "math"),
    ("k-means++ 初始化（多起點）", "k-means++ Initialization (multi-start)", "random"),
    ("Lloyd 迭代：指派與更新群中心", "K-Means (Assign to nearest μ_k, update μ_k = mean(S_k))", "Python Built-in"),
    ("SSE、群大小與輪廓係數評估", "SSE & Silhouette Evaluation", "math"),
    ("分群品質 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def run_kmeans(z_scores=None, k: int = 3, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("kmeans_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "k": k if isinstance(k, int) else None,
                       "cluster_centers": [], "labels": [], "sse": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    errors = []
    X, derr = validate_matrix(z_scores, "z_scores")
    errors += derr
    if isinstance(k, bool) or not isinstance(k, int):
        errors.append("K 必須為整數")
    elif not 1 <= k <= K_LIMIT:
        errors.append(f"K = {k} 超出範圍 [1, {K_LIMIT}]")
    elif X is not None and len(X) < max(10, 5 * k):
        errors.append(f"資料只有 {len(X)} 筆，不足以分成 {k} 群（至少需要 {max(10, 5 * k)} 筆，即每群平均 ≥5 筆）")
    if X is not None and len({tuple(r) for r in X}) < (k if isinstance(k, int) and not isinstance(k, bool) else 1):
        errors.append("資料中不同的點比群數還少，無法分群")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    warnings = column_std_warnings(X)
    n, dim = len(X), len(X[0])
    log.add(f"資料 {n} 筆 × {dim} 維，K={k}（允許 1–{K_LIMIT}）。" + ("；".join(warnings) if warnings else "各欄平均≈0、標準差≈1，符合 z 分數。"))

    # 2 + 3
    res = km.kmeans(X, k, n_init=N_INIT, seed=SEED, max_iter=MAX_ITER)
    log.add(f"以 k-means++ 選初始中心（第一個隨機，其餘依到最近中心距離² 的機率抽取），重複 {N_INIT} 次起點（固定 seed={SEED}）後取 SSE 最小者，避免落入壞的局部解。")
    log.add(f"Lloyd 迭代：把每個點歸到最近的中心（歐氏距離），再以 μ_k = 群內平均更新中心，直到指派不再改變（最佳起點 {res['n_iter']} 輪收斂；上限 {MAX_ITER} 輪）。"
            f"{N_INIT} 個起點{'全部' if res['all_inits_converged'] else '並非全部'}在上限內收斂。")

    # 4
    sizes = [res["labels"].count(j) for j in range(k)]
    sse1 = sum(sum((v - m) ** 2 for v, m in zip(x, [sum(r[d] for r in X) / n for d in range(dim)])) for x in X)
    var_exp = 1 - res["sse"] / sse1 if sse1 > 0 else None
    sil = km.silhouette(X, res["labels"], k) if k >= 2 else None
    per = []
    for j in range(k):
        within = sum(km.sqdist(x, res["centers"][j]) for x, l in zip(X, res["labels"]) if l == j)
        per.append({"cluster": j, "size": sizes[j], "share": round(sizes[j] / n, 4), "within_sse": round(within, 4),
                    "center": [round(v, 4) for v in res["centers"][j]]})
    log.add(f"SSE = {res['sse']:.2f}（K=1 時為 {sse1:.2f}，變異解釋率 {var_exp * 100:.1f}%）；群大小 " + "、".join(f"群{j}:{s}" for j, s in enumerate(sizes))
            + (f"；平均輪廓係數 {sil:.3f}。" if sil is not None else "；K=1 不計算輪廓係數。"))

    # 5
    if not res["converged"]:
        log.add("防呆檢核狀態：BLOCKED_BY_GUARDRAIL (not converged)。")
        return finish({"status": "success", "found": False, "k": k, "cluster_centers": [], "labels": [], "sse": None,
                       "warnings": [f"{MAX_ITER} 輪內未收斂"], "guardrail_status": "BLOCKED_BY_GUARDRAIL (not converged)",
                       "answer_text": f"K-Means 在 {MAX_ITER} 輪內未收斂，結果不可靠"})
    if k == 1:
        warnings.append("K=1 等於不分群，只是計算整體中心")
    tiny = [j for j, s in enumerate(sizes) if s / n < TINY_CLUSTER]
    if tiny:
        warnings.append(f"群 {', '.join(map(str, tiny))} 只占全體不到 {TINY_CLUSTER * 100:.0f}%（{', '.join(str(sizes[j]) for j in tiny)} 筆），可能是離群點自成一群而非真正的運轉模式")
    if sil is not None and sil < LOW_SILHOUETTE:
        warnings.append(f"平均輪廓係數 {sil:.2f} < {LOW_SILHOUETTE}，資料沒有實質的群結構，這個分群只是在切割連續分佈")
    elif sil is not None and sil < WEAK_SILHOUETTE:
        warnings.append(f"平均輪廓係數 {sil:.2f}（介於 {LOW_SILHOUETTE}–{WEAK_SILHOUETTE}），群結構薄弱，群與群的界線不明顯，分群結果僅供參考")
    if not res["all_inits_converged"]:
        warnings.append("部分起點未收斂")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（已收斂、無空群）。" + ("；".join(warnings) if warnings else f"各群大小皆 ≥{TINY_CLUSTER * 100:.0f}%、輪廓係數 ≥{WEAK_SILHOUETTE}。"))

    return finish({
        "status": "success", "found": True, "k": k,
        "cluster_centers": [[round(v, 4) for v in c] for c in res["centers"]], "labels": res["labels"],
        "cluster_sizes": sizes, "clusters": per, "sse": round(res["sse"], 4), "sse_k1": round(sse1, 4),
        "variance_explained": None if var_exp is None else round(var_exp, 4),
        "silhouette": None if sil is None else round(sil, 4), "n_iter": res["n_iter"], "converged": res["converged"],
        "n_points": n, "dimension": dim, "n_init": N_INIT, "seed": SEED,
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"分成 {k} 群，群大小 {sizes}，SSE={res['sse']:.2f}，解釋了 {var_exp * 100:.1f}% 的總變異"
                       + (f"，輪廓係數 {sil:.2f}。" if sil is not None else "。"),
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_20_process_parameter_kmeans ===")
    import random
    rng = random.Random(1)
    demo = [[rng.gauss(m, 0.4), rng.gauss(m, 0.4)] for m in (-1.2, 0, 1.2) for _ in range(40)]
    r = run_kmeans(demo, 3)
    r.pop("labels", None)
    print(json.dumps(r, ensure_ascii=False, indent=2))
