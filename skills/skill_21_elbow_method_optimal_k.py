"""
skill_21_elbow_method_optimal_k.py - 手肘法決定最佳群數 K 的技能

對應系統規格：US-12 / 12. 製程參數分群與 SPC 管制監控頁（呼叫順序：skill_21 → skill_20 → skill_22）
演算法機制：輸入防呆 -> 逐一 K=1..max_k 以多組 k-means++ 起點取最小 SSE -> 弦距法找手肘
            -> 輪廓係數交叉檢查 -> Guardrail

重要說明：
  * SSE 一定隨 K 增加而下降（K=資料筆數時為 0），所以「SSE 最小」不是目標，要找的是下降速度明顯變緩的轉折點。
  * 手肘是目測性質的啟發式；這裡用「弦距法」把它量化，並附上手肘強度。資料本身沒有群結構時，
    SSE 曲線近似直線，強度會很低，此時 optimal_k 不可信（會警告）。
  * 手肘強度只描述 SSE 曲線的彎曲程度，「不能」證明資料有群結構：實測沒有任何群結構的高斯雲，手肘強度也有 0.4 左右。
    判斷「資料到底有沒有群」要看輪廓係數（≥0.5 合理、0.25–0.5 薄弱、<0.25 無結構；實測無結構資料最高約 0.34–0.42，有明顯分群的約 0.5–0.7）。
  * 另外用輪廓係數（Silhouette）獨立檢查：兩種方法給出的 K 不同時會警告。
  * 輸入應為 z 分數（K-Means 對尺度敏感）。
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

SKILL_NAME = "skill_21_elbow_method_optimal_k"
MAX_K_LIMIT = 10
N_INIT = 10
SEED = 42
WEAK_ELBOW = 0.15           # 弦距強度低於此值視為沒有明顯手肘
LOW_SILHOUETTE = 0.25       # < 0.25：沒有實質群結構（Kaufman & Rousseeuw 慣用解讀）
WEAK_SILHOUETTE = 0.50      # 0.25–0.5：結構薄弱，可能只是把連續分佈切開；≥0.5 才算有合理結構

PLAN = [
    ("輸入資料與 max_k 防呆", "Boundary & Type Validation", "math"),
    ("逐一 K 以多組起點計算最小 SSE", "K-Means (k-means++ init, multi-start) SSE per K", "random, math"),
    ("弦距法判定手肘轉折點", "Elbow Method (max distance to chord)", "Python Built-in"),
    ("輪廓係數交叉檢查", "Silhouette Score Cross-check", "random, math"),
    ("轉折可信度 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def find_optimal_k(data=None, max_k: int = 8, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("elbow_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "optimal_k": None, "sse_by_k": [], "sse": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    errors = []
    if isinstance(max_k, bool) or not isinstance(max_k, int):
        errors.append("max_k 必須為整數")
    elif not 3 <= max_k <= MAX_K_LIMIT:
        errors.append(f"max_k = {max_k} 超出範圍 [3, {MAX_K_LIMIT}]（手肘法至少要比較 3 個 K）")
    X, derr = validate_matrix(data, "data")
    errors += derr
    if X is not None and isinstance(max_k, int) and not isinstance(max_k, bool):
        need = max(20, 5 * max_k)
        if len(X) < need:
            errors.append(f"資料只有 {len(X)} 筆，不足以比較到 K={max_k}（至少需要 {need} 筆，即每群平均 ≥5 筆）")
    if X is not None and len({tuple(r) for r in X}) < 3:
        errors.append("資料中不同的點少於 3 個，無法分群")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    warnings = column_std_warnings(X)
    log.add(f"資料 {len(X)} 筆 × {len(X[0])} 維，皆為有限數值；比較 K=1..{max_k}。" + ("；".join(warnings) if warnings else "各欄平均≈0、標準差≈1，符合 z 分數。"))

    # 2
    ks = list(range(1, max_k + 1))
    runs = [km.kmeans(X, k, n_init=N_INIT, seed=SEED) for k in ks]
    sses = [r["sse"] for r in runs]
    if sses[0] <= 1e-12:
        log.add("K=1 時的 SSE 為 0，所有資料點重合。")
        return blocked("資料沒有變異", "BLOCKED_BY_GUARDRAIL (no variance)", "資料沒有任何變異，無法分群")
    log.add(f"每個 K 以 k-means++ 初始化重複 {N_INIT} 次（固定 seed={SEED}）取 SSE 最小者；SSE = Σ||x-μ_k||²。結果："
            + "、".join(f"K={k}: {s:.2f}" for k, s in zip(ks, sses)) + f"。SSE 單調下降：{'是' if all(a >= b - 1e-9 for a, b in zip(sses, sses[1:])) else '否（多起點仍未找到全域最佳，請留意）'}。")

    # 3
    opt, strength, dists = km.elbow_index(ks, sses)
    if opt is None:
        return blocked("無法判定手肘", "BLOCKED_BY_GUARDRAIL (no elbow)", "SSE 曲線平坦，無法判定手肘")
    log.add(f"把 (K, SSE) 正規化到 [0,1]，計算各點到「K=1 與 K={max_k} 連線」的距離，距離最大處為手肘：K={opt}（手肘強度 {strength:.2f}，0 代表直線、越大轉折越明顯）。"
            f"K={opt} 的 SSE={sses[opt - 1]:.2f}，相當於 K=1 時的 {sses[opt - 1] / sses[0] * 100:.1f}%。")

    # 4
    sil = {}
    for k, r in zip(ks, runs):
        if k >= 2:
            sil[k] = km.silhouette(X, r["labels"], k)
    sil_valid = {k: v for k, v in sil.items() if v is not None}
    sil_best = max(sil_valid, key=lambda k: sil_valid[k]) if sil_valid else None
    log.add("平均輪廓係數（-1~1，越大群越分明）：" + "、".join(f"K={k}: {v:.3f}" for k, v in sil_valid.items())
            + (f"。輪廓係數最高的是 K={sil_best}（{sil_valid[sil_best]:.3f}）。" if sil_best else "。")
            + (f"（資料超過 {km.SIL_SAMPLE} 筆時以固定 seed 抽樣計算。）" if len(X) > km.SIL_SAMPLE else ""))

    # 5
    if sil_best is not None and sil_valid[sil_best] < LOW_SILHOUETTE:
        warnings.append(f"最高輪廓係數只有 {sil_valid[sil_best]:.2f}（< {LOW_SILHOUETTE}），資料沒有實質的群結構，任何 K 都只是在切割連續分佈")
    elif sil_best is not None and sil_valid[sil_best] < WEAK_SILHOUETTE:
        warnings.append(f"最高輪廓係數 {sil_valid[sil_best]:.2f}（介於 {LOW_SILHOUETTE}–{WEAK_SILHOUETTE}），群結構薄弱，分群可能是人為切割而非真實的運轉模式；手肘看起來明顯不代表資料真的有群")
    if strength < WEAK_ELBOW:
        warnings.append(f"手肘強度僅 {strength:.2f}（< {WEAK_ELBOW}），SSE 曲線接近直線，沒有明顯轉折，K={opt} 不可靠")
    if sil_best is not None and sil_best != opt:
        warnings.append(f"手肘法建議 K={opt}，但輪廓係數最高的是 K={sil_best}，兩種方法不一致，請由製程知識判斷")
    if opt == max_k:
        warnings.append(f"手肘落在上限 K={max_k}，可能還需要更大的 max_k（目前上限 {MAX_K_LIMIT}）")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}。" + ("；".join(warnings) if warnings else f"手肘強度 {strength:.2f} ≥ {WEAK_ELBOW}、最高輪廓係數 ≥ {WEAK_SILHOUETTE}、兩種方法給出相同的 K、資料已標準化。"))

    return finish({
        "status": "success", "found": True, "optimal_k": opt, "sse": round(sses[opt - 1], 4),
        "sse_by_k": [round(s, 4) for s in sses], "k_values": ks, "elbow_strength": round(strength, 4),
        "elbow_distances": [round(d * (2 ** 0.5), 4) for d in dists],
        "silhouette_by_k": {str(k): (None if v is None else round(v, 4)) for k, v in sil.items()},
        "silhouette_best_k": sil_best, "n_points": len(X), "n_init": N_INIT, "seed": SEED,
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"手肘法建議分成 K={opt} 群（SSE={sses[opt - 1]:.2f}，手肘強度 {strength:.2f}）"
                       + (f"；輪廓係數同樣支持 K={sil_best}。" if sil_best == opt else (f"；但輪廓係數最高的是 K={sil_best}。" if sil_best else "。")),
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_21_elbow_method_optimal_k ===")
    import random
    rng = random.Random(1)
    demo = [[rng.gauss(m, 0.4), rng.gauss(m, 0.4)] for m in (-2, 0, 2) for _ in range(40)]
    print(json.dumps(find_optimal_k(demo, 8), ensure_ascii=False, indent=2))
