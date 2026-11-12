"""
skill_22_spc_control_limit_monitoring.py - SPC 管制界限（Mean ± 3σ）與異常點監控技能

對應系統規格：US-13 / 12. 製程參數分群與 SPC 管制監控頁（呼叫順序：skill_21 → skill_20 → skill_22）
演算法機制：序列防呆 -> 基準期平均與標準差 -> UCL/LCL = μ ± 3σ -> 超界點與輔助判異規則 -> Guardrail

說明（請務必讀）：
  * 規格定義：UCL = μ + 3σ、LCL = μ - 3σ，超出者為異常點。σ 用樣本標準差（n-1）。
  * 若輸入本身就是「用同一份資料算出的 z 分數」，平均必為 0、標準差必為 1，限界必然是 ±3
    （規格範例的 ucl 3.0 / lcl -3.0 正是這個原因）。此時管制圖只是在檢查 |z|>3，並不是獨立的管制標準，
    系統會明確警告。用 baseline_n 指定「前 N 點為基準期」可避免這個同義反覆，也更接近實務 Phase I / Phase II 的做法。
  * 用全部資料算 σ 時，異常點本身會把 σ 撐大，使限界變寬；因此另外提供個別值移動全距（I-MR）的穩健 σ 對照：
    σ̂ = MR̄ / 1.128（MR 為相鄰點差的絕對值）。兩種 σ 差異很大代表序列有位移、趨勢或混合模式。
  * 輔助規則：連續 8 點落在中心線同一側（疑似位移）；lag-1 自相關 > 0.5（個別值管制圖的獨立性假設可能不成立）。
    這些只給警告，不計入 outliers_count。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
except ImportError:
    from _common import StepLog, default_output_path, save_json

SKILL_NAME = "skill_22_spc_control_limit_monitoring"
SIGMA_MULT = 3.0
MIN_POINTS = 20
MAX_POINTS = 20000
D2 = 1.128                  # n=2 的管制圖常數（移動全距 → σ）
RUN_LEN = 8
OUT_RATE_WARN = 0.10
SIGMA_GAP_WARN = 0.30
AUTOCORR_WARN = 0.50

PLAN = [
    ("數據序列與基準期防呆", "Boundary & Type Validation", "math"),
    ("計算基準期平均與標準差", "Sample Mean & Standard Deviation (n-1)", "statistics"),
    ("計算管制界限 UCL / LCL", "Shewhart Control Limits  μ ± 3σ", "Python Built-in"),
    ("標出超界點與輔助判異規則", "Out-of-control Detection & Run Rule & I-MR σ Cross-check", "Python Built-in"),
    ("管制圖可信度 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def _mean_std(v):
    m = sum(v) / len(v)
    return m, math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def monitor_spc(data_series=None, baseline_n=None, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("spc_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "spc_limits": None, "outliers_count": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # 1
    errors = []
    series = None
    if not isinstance(data_series, (list, tuple)) or not data_series:
        errors.append("data_series 必須是非空的數值陣列")
    elif len(data_series) > MAX_POINTS:
        errors.append(f"資料共 {len(data_series)} 點，超過上限 {MAX_POINTS}")
    else:
        for i, v in enumerate(data_series):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                errors.append(f"第 {i + 1} 個值不是數值")
                break
            if not math.isfinite(v):
                errors.append(f"第 {i + 1} 個值是 NaN 或無限大")
                break
        else:
            series = [float(v) for v in data_series]
            if len(series) < MIN_POINTS:
                errors.append(f"只有 {len(series)} 個點，管制界限至少需要 {MIN_POINTS} 個點才有意義")
    nb = None
    if baseline_n is not None:
        if isinstance(baseline_n, bool) or not isinstance(baseline_n, int):
            errors.append("baseline_n 必須為整數或不提供")
        elif series is not None and not MIN_POINTS <= baseline_n <= len(series):
            errors.append(f"baseline_n = {baseline_n} 需介於 [{MIN_POINTS}, {len(series)}]")
        else:
            nb = baseline_n
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    n = len(series)
    base = series[:nb] if nb else series
    log.add(f"序列共 {n} 個有限數值（按時間順序）；" + (f"以前 {nb} 點作為基準期計算界限，再用全部 {n} 點檢查。" if nb else f"以全部 {n} 點同時計算界限並檢查（規格預設做法）。"))

    # 2
    mu, sigma = _mean_std(base)
    if sigma <= 1e-12:
        log.add(f"基準期平均 {mu:.4f}、標準差 {sigma:.2e}：數值幾乎沒有變異，無法建立管制界限。")
        return blocked("標準差為 0", "BLOCKED_BY_GUARDRAIL (no variance)", "基準期的數值完全相同（標準差為 0），無法建立管制界限")
    log.add(f"基準期 {len(base)} 點：平均 μ = {mu:.4f}、樣本標準差 σ = {sigma:.4f}（分母 n-1）。")

    # 3
    ucl, lcl = mu + SIGMA_MULT * sigma, mu - SIGMA_MULT * sigma
    log.add(f"UCL = μ + 3σ = {mu:.4f} + 3×{sigma:.4f} = {ucl:.4f}；LCL = μ - 3σ = {lcl:.4f}；中心線 CL = μ = {mu:.4f}。")

    # 4
    out_idx = [i for i, v in enumerate(series) if v > ucl or v < lcl]
    runs, i = [], 0
    while i < n:
        side = series[i] > mu
        j = i
        while j + 1 < n and (series[j + 1] > mu) == side:
            j += 1
        if j - i + 1 >= RUN_LEN:
            runs.append({"start": i, "end": j, "length": j - i + 1, "side": "above" if side else "below"})
        i = j + 1
    mr = [abs(series[k] - series[k - 1]) for k in range(1, n)]
    sigma_mr = (sum(mr) / len(mr)) / D2
    r_ucl, r_lcl = mu + 3 * sigma_mr, mu - 3 * sigma_mr
    r_out = [k for k, v in enumerate(series) if v > r_ucl or v < r_lcl]
    ms, ss = _mean_std(series)
    lag1 = (sum((series[k] - ms) * (series[k - 1] - ms) for k in range(1, n)) / sum((v - ms) ** 2 for v in series)) if ss > 0 else 0.0
    log.add(f"超出 [{lcl:.3f}, {ucl:.3f}] 的點共 {len(out_idx)} 個（位置 {', '.join(str(k) for k in out_idx[:10])}{'…' if len(out_idx) > 10 else ''}）。"
            f"輔助檢查：連續 {RUN_LEN} 點同側的區段 {len(runs)} 處；lag-1 自相關 {lag1:.2f}；以相鄰點差估計的穩健 σ(I-MR) = MR̄/1.128 = {sigma_mr:.4f}"
            f"（對照樣本 σ={sigma:.4f}），以它算出的限界會抓到 {len(r_out)} 點。")

    # 5
    warnings = []
    if abs(mu) < 1e-6 and abs(sigma - 1) < 1e-6 and not nb:
        warnings.append("輸入本身就是以同一份資料算出的 z 分數（平均 0、標準差 1），限界必然是 ±3，等於只在檢查 |z|>3，不是獨立於資料的管制標準；建議指定基準期 baseline_n")
    if len(out_idx) / n > OUT_RATE_WARN:
        warnings.append(f"{len(out_idx) / n * 100:.0f}% 的點超出管制界限（> {OUT_RATE_WARN * 100:.0f}%），製程可能不穩定，或這個界限不適用於這份資料（例如混合了多種運轉模式）")
    gap = abs(sigma - sigma_mr) / sigma_mr if sigma_mr > 0 else 0
    if gap > SIGMA_GAP_WARN:
        warnings.append(f"樣本 σ（{sigma:.3f}）與穩健 σ（{sigma_mr:.3f}）相差 {gap * 100:.0f}%（> {SIGMA_GAP_WARN * 100:.0f}%），序列可能含有位移、趨勢、混合模式或離群點，Mean±3σ 的限界可信度低")
    if runs:
        warnings.append(f"發現 {len(runs)} 段連續 {RUN_LEN} 點以上落在中心線同一側（最長 {max(r['length'] for r in runs)} 點），疑似製程平均位移，即使沒有點超界也需留意")
    if abs(lag1) > AUTOCORR_WARN:
        warnings.append(f"lag-1 自相關 {lag1:.2f}（|r| > {AUTOCORR_WARN}），相鄰點不獨立，個別值管制圖的誤報率會失真")
    if nb and nb < 2 * MIN_POINTS:
        warnings.append(f"基準期只有 {nb} 點，界限估計不穩定（建議 ≥ {2 * MIN_POINTS} 點）")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}（≥{MIN_POINTS} 點、σ>0）。" + ("；".join(warnings) if warnings else "出界比例、兩種 σ 的一致性與自相關皆在合理範圍。"))

    return finish({
        "status": "success", "found": True,
        "spc_limits": {"ucl": round(ucl, 4), "lcl": round(lcl, 4), "center": round(mu, 4), "sigma": round(sigma, 4)},
        "outliers_count": len(out_idx), "outlier_indices": out_idx,
        "outliers": [{"index": k, "value": round(series[k], 4), "side": "above" if series[k] > ucl else "below"} for k in out_idx[:50]],
        "robust": {"sigma_imr": round(sigma_mr, 4), "ucl": round(r_ucl, 4), "lcl": round(r_lcl, 4), "outliers_count": len(r_out)},
        "run_violations": runs, "lag1_autocorrelation": round(lag1, 4),
        "n_points": n, "baseline_n": nb, "basis": "baseline" if nb else "all_points",
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"UCL={ucl:.3f}、LCL={lcl:.3f}，{n} 點中有 {len(out_idx)} 點超出管制界限"
                       + ("（建議留意位移）。" if runs else "。"),
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_22_spc_control_limit_monitoring ===")
    import random
    rng = random.Random(2)
    demo = [rng.gauss(0, 1) for _ in range(100)]
    demo[30], demo[70] = 6.0, -5.5
    print(json.dumps(monitor_spc(demo, baseline_n=60), ensure_ascii=False, indent=2))
