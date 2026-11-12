# -*- coding: utf-8 -*-
"""
skill_07_risk_level_classification — 勝算比 (Odds Ratio) 與風險燈號劃分

對應：US-04 / 選單 07. 設備突發故障風險評估頁
  odds = p / (1-p)；燈號：p ≥ θ → RED；p ≥ θ×yellow_ratio → YELLOW；否則 GREEN
  θ 為預警門檻（通常來自 skill_08 的成本最佳門檻；未提供時以預設成本矩陣算出）
純標準庫。
"""
import math

try:
    from . import failure_core as fc
    from . import skill_common as sc
except ImportError:
    import failure_core as fc
    import skill_common as sc

SKILL = "skill_07_risk_level_classification"
DEFAULT_COST_DOWN = 50000.0
DEFAULT_COST_INSPECT = 2000.0
P_EPS = 1e-9


def classify_risk_level(failure_probability=0.5, optimal_threshold=None, yellow_ratio=0.5,
                        output_json_path=None, **_ignored):
    steps = []

    def add(name, desc, algo, pkg):
        steps.append(sc.make_step(len(steps) + 1, name, desc, SKILL, algo, pkg))

    # ── 步驟 1：機率有效性 Guardrail ────────────────────────────
    try:
        p = float(failure_probability)
        valid = math.isfinite(p) and 0.0 <= p <= 1.0
    except (TypeError, ValueError):
        p, valid = None, False
    add("故障機率有效性 Guardrail",
        f"收到 failure_probability={failure_probability!r}；" + ("位於 [0, 1]，通過。" if valid else "必須是 0~1 的有限數值，未通過。"),
        "Range Guardrail", "math")
    if not valid:
        result = {"status": "success", "found": False,
                  "answer_text": f"故障機率必須介於 0 到 1，收到：{failure_probability!r}。",
                  "warnings": ["failure_probability 超出 [0,1]"], "data_source": "", "steps": steps}
        sc.save_json(result, "risk_level_result.json", output_json_path)
        return result

    # ── 步驟 2：勝算與 logit ───────────────────────────────────
    pc = min(max(p, P_EPS), 1.0 - P_EPS)
    odds = pc / (1.0 - pc)
    logit = math.log(odds)
    add("計算勝算 (Odds) 與 logit",
        f"Odds = p/(1-p) = {pc:.4f}/{1 - pc:.4f} = {odds:.4f}（故障發生 : 不發生 ≈ {odds:.2f} : 1）；logit = ln(Odds) = {logit:+.3f}。"
        + ("（p 觸及 0/1，已夾限在 1e-9 以避免除以零。）" if pc != p else ""),
        "Odds Ratio  Odds=p/(1-p)", "math")

    # ── 步驟 3：單位勝算比（e^w）────────────────────────────────
    model = fc.get_model()
    feature_or = {k: round(math.exp(model["w_raw"][k]), 4) for k in fc.KEYS}
    add("各特徵單位勝算比 e^w",
        "每增加 1 單位，故障勝算變為原來的：" + "；".join(f"{fc.LABELS[k]}（{fc.UNITS[k]}）×{feature_or[k]:.3f}" for k in fc.KEYS)
        + "。>1 表示增加故障風險。",
        "Odds Ratio  OR=e^w", "math")

    # ── 步驟 4：取得預警門檻 θ ─────────────────────────────────
    th_source = "呼叫端提供（通常來自 skill_08 成本最佳門檻）"
    try:
        theta = None if optimal_threshold is None else float(optimal_threshold)
        if theta is not None and not (math.isfinite(theta) and 0.0 < theta <= 1.0):
            raise ValueError
    except (TypeError, ValueError):
        theta, th_source = None, "提供值不合法，改用預設"
    if theta is None:
        try:
            from . import skill_08_cost_sensitive_threshold_tuning as s08
        except ImportError:
            import skill_08_cost_sensitive_threshold_tuning as s08
        res08 = s08.tune_cost_sensitive_threshold(DEFAULT_COST_DOWN, DEFAULT_COST_INSPECT,
                                                  output_json_path=_null_path())
        theta = res08.get("optimal_threshold") or 0.5
        if th_source == "提供值不合法，改用預設":
            th_source += f"（預設成本 {DEFAULT_COST_DOWN:g}/{DEFAULT_COST_INSPECT:g}）"
        else:
            th_source = f"未提供，以預設成本矩陣（停機 {DEFAULT_COST_DOWN:g} / 誤報 {DEFAULT_COST_INSPECT:g}）算出"
    try:
        yr = float(yellow_ratio)
        if not (0.0 < yr < 1.0):
            raise ValueError
    except (TypeError, ValueError):
        yr = 0.5
    yellow_th = round(theta * yr, 4)
    add("取得預警門檻 θ", f"θ = {theta:.2f}（{th_source}）；黃燈下限 = θ × {yr:g} = {yellow_th:.2f}。",
        "Cost-sensitive Threshold (引用 skill_08)", "math")

    # ── 步驟 5：燈號劃分 ───────────────────────────────────────
    if p >= theta:
        level, action = "RED", "機率已達預警門檻，建議派員檢修或排定停機檢查。"
    elif p >= yellow_th:
        level, action = "YELLOW", "機率偏高但未達門檻，建議加密巡檢並追蹤警報趨勢。"
    else:
        level, action = "GREEN", "風險低於黃燈下限，維持例行保養即可。"
    add("風險燈號劃分",
        f"p={p:.4f} vs θ={theta:.2f}、黃燈下限 {yellow_th:.2f} → {level}。",
        "Threshold-based Risk Classification", "math")

    result = {
        "status": "success", "found": True, "data_source": model["data_source"],
        "failure_probability": round(p, 4), "odds_ratio": round(odds, 4), "logit": round(logit, 4),
        "risk_level": level, "optimal_threshold": theta, "yellow_threshold": yellow_th,
        "feature_odds_ratios": feature_or, "warnings": [],
        "answer_text": f"故障機率 {p:.1%}、勝算比 {odds:.2f}，風險燈號 {level}。{action}",
        "steps": steps,
    }
    sc.save_json(result, "risk_level_result.json", output_json_path)
    return result


def _null_path():
    """內部呼叫 skill_08 取預設門檻時，不要覆寫使用者真正的 skill_08 輸出檔。"""
    import os
    return os.path.join(sc.project_root(), "output", "_internal_default_threshold.json")
