"""
skill_07_risk_level_classification.py - 勝算比與風險燈號劃分技能

對應系統規格：US-04 / 07. 設備突發故障風險評估頁
演算法機制：機率與門檻防呆 -> 機率截斷 -> 勝算比 Odds = p/(1-p) = e^(wᵀx+b)
            -> 紅黃綠燈號劃分 -> 飽和機率 Guardrail

說明：規格書寫 Odds = e^(wᵀx)，但其範例（p=0.84 → 5.25）是 p/(1-p)，
即 e^(wᵀx+b)（z 含截距），本技能採後者。
燈號門檻預設：GREEN < 0.40 ≤ YELLOW < 0.70 ≤ RED，可由參數覆寫。
"""

import json
import math

try:
    from ._common import StepLog, default_output_path, save_json
    from ._failure_model import PROB_EPS, clean_num
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _failure_model import PROB_EPS, clean_num

SKILL_NAME = "skill_07_risk_level_classification"
DEFAULT_YELLOW = 0.40
DEFAULT_RED = 0.70

PLAN = [
    ("故障機率與燈號門檻防呆", "Boundary & Type Validation", "math"),
    ("機率邊界截斷", "Probability Clipping [ε, 1-ε]", "math"),
    ("勝算比與對數勝算計算", "Odds Ratio  p/(1-p) = e^z", "math"),
    ("紅黃綠風險燈號劃分", "Threshold Band Classification", "Python Control Flow"),
    ("飽和機率 Guardrail 檢核與處置建議生成", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]

LEVEL_META = {
    "RED": ("紅燈：高風險", "建議立即安排停機檢修，並備妥關鍵備品。"),
    "YELLOW": ("黃燈：注意", "建議縮短巡檢週期並於近期排入檢修。"),
    "GREEN": ("綠燈：正常", "維持例行巡檢，持續監控警報次數與壓力。"),
}


def classify_risk_level(
    failure_probability=None, yellow_threshold=DEFAULT_YELLOW, red_threshold=DEFAULT_RED,
    output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("risk_level_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    p_echo = clean_num(failure_probability)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    # 1. 防呆
    errors = []
    p = failure_probability
    if p is None:
        errors.append("缺少 failure_probability（前一步的故障機率計算可能被 Guardrail 攔截）")
    elif isinstance(p, bool) or not isinstance(p, (int, float)):
        errors.append("failure_probability 必須為數值")
    elif not math.isfinite(p):
        errors.append("failure_probability 不可為 NaN 或無限大")
    elif not 0.0 <= p <= 1.0:
        errors.append(f"failure_probability = {p:g} 必須介於 0 到 1")

    for name, v in (("yellow_threshold", yellow_threshold), ("red_threshold", red_threshold)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            errors.append(f"{name} 必須為有限數值")
    if not errors and not 0.0 < yellow_threshold < red_threshold < 1.0:
        errors.append(f"燈號門檻需滿足 0 < yellow < red < 1（收到 yellow={yellow_threshold:g}, red={red_threshold:g}）")

    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        log.skip_to_last("輸入未通過驗證")
        guardrail = "BLOCKED_BY_GUARDRAIL (invalid input)"
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "failure_probability": p_echo,
                       "odds_ratio": None, "risk_level": None, "warnings": errors,
                       "guardrail_status": guardrail, "answer_text": "輸入未通過驗證：" + "；".join(errors)})
    log.add(f"故障機率 {p:.4f} 為 [0,1] 內的有限數值；燈號門檻 黃 {yellow_threshold:g} / 紅 {red_threshold:g} 設定合理。")

    # 2. 截斷
    p_used = min(max(float(p), PROB_EPS), 1.0 - PROB_EPS)
    clipped = p_used != float(p)
    log.add(f"為避免 p=0 或 p=1 時勝算比為 0 / 無限大，將機率截斷至 [{PROB_EPS:g}, {1 - PROB_EPS:.6f}]"
            + (f"（本次由 {p:g} 截為 {p_used:g}）。" if clipped else "（本次無需截斷）。"))

    # 3. 勝算比
    odds = p_used / (1.0 - p_used)
    log_odds = math.log(odds)
    log.add(f"Odds = p/(1-p) = {p_used:.4f}/{1 - p_used:.4f} = {odds:.4f}；對數勝算 ln(Odds) = {log_odds:+.4f}"
            "（即線性分數 z = wᵀx + b）。")

    # 4. 燈號
    if p_used >= red_threshold:
        level = "RED"
    elif p_used >= yellow_threshold:
        level = "YELLOW"
    else:
        level = "GREEN"
    label, action = LEVEL_META[level]
    log.add(f"依門檻劃分：p={p_used:.4f}，黃 ≥ {yellow_threshold:g}、紅 ≥ {red_threshold:g} → {level}。")

    # 5. Guardrail
    warnings = []
    if p_used <= 0.001 or p_used >= 0.999:
        warnings.append("機率已接近 0 或 1（Sigmoid 飽和），此時勝算比的數值意義有限，請以燈號與工況為主")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}。" + ("；".join(warnings) if warnings else "機率未飽和，勝算比可正常解讀。"))

    answer = (f"{label}。故障勝算比 {odds:.2f}：故障發生的可能性是不發生的 {odds:.2f} 倍"
              if odds >= 1 else
              f"{label}。故障勝算比 {odds:.2f}：故障發生的可能性僅為不發生的 {odds:.2f} 倍")
    return finish({
        "status": "success", "found": True,
        "failure_probability": round(float(p), 4), "probability_used": round(p_used, 6),
        "odds_ratio": round(odds, 4), "log_odds": round(log_odds, 4),
        "risk_level": level, "risk_label": label, "recommended_action": action,
        "thresholds": {"yellow": yellow_threshold, "red": red_threshold},
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": f"{answer}。{action}",
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_07_risk_level_classification ===")
    print(json.dumps(classify_risk_level(0.84), ensure_ascii=False, indent=2))
