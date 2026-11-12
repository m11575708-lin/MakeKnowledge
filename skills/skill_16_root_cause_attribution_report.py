"""
skill_16_root_cause_attribution_report.py - 品質異常根因歸因報告技能

對應系統規格：US-09 / 10. 品質異常根本原因分析頁
演算法機制：整合 skill_14（預測）與 skill_15（MDI 排序）-> 計算批次偏離量
            -> 歸因分數 = 重要度 × |偏離 z| -> 根因判定與處置建議 -> Guardrail

歸因邏輯（我的設計，不是標準演算法，請當作啟發式）：
  * 全域重要度（skill_15）只說明模型依賴哪個參數；要回答「這一批」的主因，還要看這一批在該參數上偏離良品多遠。
  * 偏離量 dev_i = (x_i - 良品樣本平均_i) / 全體標準差_i；歸因分數 = MDI_i × |dev_i|；占比 = 分數 / 總和。
  * 這是相關性層面的歸因，不能證明因果；處置建議為手寫的示範規則，須由製程工程師確認。
"""

import json

try:
    from ._common import StepLog, default_output_path, save_json
    from ._quality_data import FEATURES, LABELS, UNITS, clean_num
    from ._quality_model import get_model, resolve_batch, validate_n_trees
    from .skill_14_yield_rate_anomaly_detection import detect_yield_anomaly
    from .skill_15_feature_importance_ranking import rank_feature_importance
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _quality_data import FEATURES, LABELS, UNITS, clean_num
    from _quality_model import get_model, resolve_batch, validate_n_trees
    from skill_14_yield_rate_anomaly_detection import detect_yield_anomaly
    from skill_15_feature_importance_ranking import rank_feature_importance

SKILL_NAME = "skill_16_root_cause_attribution_report"
DOMINANT_SHARE = 0.50     # 占比達此值視為有明確主因
RISK_ALERT = 0.50         # 不良機率達此值視為高風險
NEAR_ZERO_DEV = 0.5       # 所有參數偏離都小於此 |z| 時，不宜指認根因

ACTIONS = {
    ("temp", "high"): ("REDUCE_HEATING_TEMP", "降低加熱爐設定溫度，並確認熱電偶校正與爐溫均勻度"),
    ("temp", "low"): ("RAISE_HEATING_TEMP", "提高加熱爐設定溫度，並檢查燃燒器與爐門密封"),
    ("cooling", "low"): ("INCREASE_COOLING_FLOW", "提高冷卻水流量，並檢查濾網、閥門與管路是否阻塞"),
    ("cooling", "high"): ("REDUCE_COOLING_FLOW", "降低冷卻水流量，避免過度冷卻造成殘留應力"),
    ("speed", "high"): ("REDUCE_ROLLING_SPEED", "降低軋延速度，並確認軋輥負載與潤滑狀態"),
    ("speed", "low"): ("RAISE_ROLLING_SPEED", "檢查軋延速度設定是否過低，確認與加熱溫度的節拍是否匹配"),
}

PLAN = [
    ("前置預測與重要度結果檢核", "Upstream Result Validation", "math"),
    ("計算批次參數偏離量", "Z-Score Deviation from Good-batch Baseline", "statistics"),
    ("計算歸因分數  重要度 × |偏離|", "Importance-weighted Deviation Attribution", "Python Built-in"),
    ("根因判定與處置建議", "Argmax Attribution & Rule-based Recommendation", "Python Built-in"),
    ("歸因可信度 Guardrail 檢核", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def build_root_cause_report(batch_id=None, batch_params=None, n_trees: int = 100,
                            prediction: dict = None, importance: dict = None,
                            output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("root_cause_report.json")
    log = StepLog(SKILL_NAME, PLAN)

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "batch_id": batch_id, "root_cause_feature": None,
                       "risk_score": None, "action_recommendation": None, "warnings": warnings or [message],
                       "guardrail_status": guardrail, "answer_text": message})

    # 1. 前置結果
    n, n_err = validate_n_trees(n_trees)
    params, batch, errors, _ = resolve_batch(batch_id, batch_params)
    errors = list(errors or []) + ([n_err] if n_err else [])
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    pred = prediction or detect_yield_anomaly(batch_params=params, batch_id=batch_id if batch_params is None else None, n_trees=n)
    imp = importance or rank_feature_importance(batch_id=batch_id, n_trees=n)
    origin = "沿用先前執行的 skill_14 / skill_15 結果" if (prediction and importance) else "重新呼叫 skill_14 / skill_15"
    if not pred.get("found") or not imp.get("found"):
        why = [f"skill_14：{pred.get('answer_text')}" for _ in [0] if not pred.get("found")] + \
              [f"skill_15：{imp.get('answer_text')}" for _ in [0] if not imp.get("found")]
        log.add(f"{origin}；上游被 Guardrail 攔截或失敗：" + "；".join(why))
        return blocked("上游結果不可用", "BLOCKED_BY_GUARDRAIL (upstream unavailable)",
                       "上游分析未通過安全檢核，無法產生根因報告：" + "；".join(why), why)
    if pred.get("batch_params") != params:
        log.add("上游預測的批次參數與本次請求不一致，已拒絕使用。")
        return blocked("上游結果與請求不一致", "BLOCKED_BY_GUARDRAIL (upstream mismatch)", "上游預測結果與要分析的批次參數不一致")
    risk = pred["defect_probability"]
    log.add(f"{origin}。預估良率 {pred['yield_rate_prediction'] * 100:.1f}%、不良機率（風險分數）{risk:.3f}、"
            f"判定 {pred['status_label']}（{pred['votes_anomaly']}/{pred['votes_total']} 棵樹投異常）；MDI 排名第一為「{imp['top_feature_label']}」。")

    # 2. 偏離
    model = get_model(n)
    imp_map = {r["feature"]: r["importance"] for r in imp["feature_importance"]}
    dev = {}
    for f, v in zip(FEATURES, params):
        st = model["stats"][f]
        dev[f] = (v - st["good_mean"]) / st["std"]
    log.add("以訓練集中「良品」的平均值為基準線，偏離 z = (本批數值 - 良品平均) / 全體標準差：" + "；".join(
        f"{LABELS[f]} {v:g}{UNITS[f]}（良品平均 {model['stats'][f]['good_mean']:.1f}）→ z={dev[f]:+.2f}" for f, v in zip(FEATURES, params)) + "。")

    # 3. 歸因分數
    score = {f: imp_map[f] * abs(dev[f]) for f in FEATURES}
    total = sum(score.values())
    share = {f: (score[f] / total if total > 0 else 0.0) for f in FEATURES}
    log.add("歸因分數 = MDI 重要度 × |偏離 z|：" + "；".join(
        f"{LABELS[f]} {imp_map[f]:.3f}×{abs(dev[f]):.2f}={score[f]:.3f}（占 {share[f] * 100:.0f}%）" for f in FEATURES) + "。")

    # 4. 根因與建議
    root = max(FEATURES, key=lambda f: score[f])
    direction = "high" if dev[root] > 0 else "low"
    code, text = ACTIONS[(root, direction)]
    log.add(f"歸因占比最高者為「{LABELS[root]}」（{share[root] * 100:.0f}%），本批數值{'偏高' if direction == 'high' else '偏低'}；"
            f"對應處置規則 {code}：{text}。")

    # 5. Guardrail
    warnings = list(pred.get("warnings", [])) + [w for w in imp.get("warnings", []) if w not in pred.get("warnings", [])]
    anomaly = pred["ensemble_prediction"] == 1 or risk >= RISK_ALERT
    max_dev = max(abs(v) for v in dev.values())
    reportable = True
    if not anomaly:
        warnings.append("本批次未被判定為品質異常，以下為偏離良品基準最大的參數，僅供參考，不應視為根因")
    if max_dev < NEAR_ZERO_DEV:
        warnings.append(f"所有參數與良品基準的偏離都小於 {NEAR_ZERO_DEV:g} 個標準差，無法指認出任何偏離的參數")
        reportable = False
    elif share[root] < DOMINANT_SHARE and anomaly:
        sec = sorted(FEATURES, key=lambda f: -score[f])[1]
        warnings.append(f"「{LABELS[root]}」占比僅 {share[root] * 100:.0f}%，並非壓倒性主因，「{LABELS[sec]}」（{share[sec] * 100:.0f}%）也需一併檢查")
    warnings.append("此歸因為相關性啟發式（重要度×偏離），不能證明因果；處置建議為示範規則，請由製程工程師確認")
    real_warn = [w for w in warnings if not w.startswith("此歸因為相關性")]
    guardrail = "PASSED" if not real_warn else "PASSED_WITH_WARNINGS"
    log.add(f"防呆檢核狀態：{guardrail}。" + ("；".join(real_warn) if real_warn else "異常判定、歸因占比與偏離量都在可解讀範圍內。"))

    contributions = [{"feature": f, "label": LABELS[f], "unit": UNITS[f], "value": params[i], "good_mean": round(model["stats"][f]["good_mean"], 3),
                      "deviation_z": round(dev[f], 3), "importance": imp_map[f], "attribution_score": round(score[f], 4),
                      "attribution_share": round(share[f], 4)} for i, f in enumerate(FEATURES)]
    contributions.sort(key=lambda c: -c["attribution_score"])
    if reportable:
        answer = (f"根因指向「{LABELS[root]}」（歸因占比 {share[root] * 100:.0f}%，風險分數 {risk:.2f}）。建議：{text}。"
                  if anomaly else f"本批次未判定為異常（風險分數 {risk:.2f}）；偏離基準最大的是「{LABELS[root]}」，僅供參考。")
    else:
        answer = f"本批次各參數都接近良品基準（風險分數 {risk:.2f}），沒有可指認的根因。"
    return finish({
        "status": "success", "found": True, "batch_id": batch["batch_id"] if batch else batch_id, "batch_params": params,
        "root_cause_feature": root if reportable else None, "root_cause_label": LABELS[root] if reportable else None,
        "root_cause_direction": direction if reportable else None,
        "risk_score": round(risk, 4), "anomaly_detected": anomaly,
        "action_recommendation": text if (reportable and anomaly) else None,
        "action_code": code if (reportable and anomaly) else None,
        "contributions": contributions, "n_trees": n,
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_16_root_cause_attribution_report ===")
    print(json.dumps(build_root_cause_report("B-2026-10"), ensure_ascii=False, indent=2))
