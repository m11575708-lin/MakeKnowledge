"""
_import_registry.py - 匯入後「發佈為分析資料集」與「重跑模型類 Skill」（page03 使用）

規格流程：匯入完成後，感測器／製程等結構化 CSV 交給對應的模型類 Skill 重跑，結果存成 JSON。
本系統各分析頁讀的是 data/ 底下固定檔名的 CSV（沒有時退回示範資料），因此「發佈」就是：
  1. 檢查欄位與數值（必要欄位、數值欄位為有限數字、至少 MIN_ROWS 列）
  2. 舊檔先備份到 data/backup/（保留最近 5 份），再以原子替換寫入新檔
  3. 用各資料集真正的載入函式確認「讀得進來」；若載入函式悄悄退回示範資料 → 立刻還原，回報失敗
  4. 重跑該資料集相關的 Skill（各 Skill 本來就會把結果存成 data/*.json）
欄位對不上任何已知資料集的 CSV 只會被收進文件索引，不會發佈。
"""

import csv
import importlib
import math
import os
import shutil
from datetime import datetime

try:
    from ._common import project_root
except ImportError:
    from _common import project_root

MIN_ROWS = 10
KEEP_BACKUPS = 5

DATASETS = {
    "sensor_history": {"label": "感測器歷史資料（壽命預測）", "filename": "sensor_history.csv",
                       "required": ["operating_hours", "vibration", "temperature", "load_rate", "rul_hours"],
                       "numeric": ["operating_hours", "vibration", "temperature", "load_rate", "rul_hours"],
                       "loader": ("skill_03_sensor_data_preprocessing", "load_reference_dataset"), "pages": "06"},
    "failure_history": {"label": "故障歷史資料（故障風險）", "filename": "failure_history.csv",
                        "required": ["recency_days", "alarms_90d", "pressure", "failed"],
                        "numeric": ["recency_days", "alarms_90d", "pressure", "failed"],
                        "loader": ("_failure_model", "load_reference_dataset"), "pages": "07"},
    "process_quality": {"label": "製程品質資料（根因分析）", "filename": "process_quality.csv",
                        "required": ["temp", "cooling", "speed", "defect"], "numeric": ["temp", "cooling", "speed", "defect"],
                        "loader": ("_quality_data", "load_samples"), "pages": "10"},
    "batches": {"label": "批次良率資料（根因分析）", "filename": "batches.csv",
                "required": ["batch_id", "temp", "cooling", "speed", "yield_rate"], "numeric": ["temp", "cooling", "speed", "yield_rate"],
                "loader": ("_quality_data", "load_batches"), "pages": "10"},
    "steel_defects": {"label": "鋼板缺陷資料（缺陷分類）", "filename": "steel_defects.csv",
                      "required": ["area", "aspect_ratio", "contrast", "defect_class"], "numeric": ["area", "aspect_ratio", "contrast"],
                      "loader": ("_steel_model", "load_data"), "pages": "11"},
    "process_params": {"label": "製程參數資料（分群與 SPC）", "filename": "process_params.csv",
                       "required": ["temp", "pressure"], "numeric": ["temp", "pressure"],
                       "loader": ("_spc_data", "load_data"), "pages": "12"},
    "ipi_monthly": {"label": "月度 IPI 資料（指數預測）", "filename": "ipi_monthly.csv",
                    "required": ["month", "ipi", "export_orders", "utilization"], "numeric": ["ipi", "export_orders", "utilization"],
                    "loader": ("_ipi_data", "load_data"), "pages": "13"},
    "equipment_risk": {"label": "設備風險指標（預防維護）", "filename": "equipment_risk.csv",
                       "required": ["equipment_id", "zone", "failure_rate", "mtbf_hours", "load_pct"],
                       "numeric": ["failure_rate", "mtbf_hours", "load_pct"],
                       "loader": ("_equipment_data", "load_data"), "pages": "13"},
}


def detect_dataset(headers):
    """欄位是某資料集必要欄位的超集合時回傳 key；多個符合時取必要欄位最多者；否則 None。"""
    hs = set(headers or [])
    hits = [(len(d["required"]), k) for k, d in DATASETS.items() if set(d["required"]) <= hs]
    return max(hits)[1] if hits else None


def _data_dir():
    return os.path.join(project_root(), "data")


def _module(name):
    pkg = __package__
    if pkg:
        return importlib.import_module("." + name, package=pkg)
    return importlib.import_module(name)


def validate_dataset_csv(path, key):
    """回傳 (rows 數, 錯誤清單)。"""
    d = DATASETS[key]
    errors = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(d["required"]) <= set(reader.fieldnames):
            return 0, [f"欄位需包含 {d['required']}"]
        n = 0
        for rec in reader:
            n += 1
            for c in d["numeric"]:
                try:
                    if not math.isfinite(float(rec[c])):
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(f"第 {n} 列的 {c} 不是有限數值")
                    break
            if len(errors) >= 5:
                break
    if not errors and n < MIN_ROWS:
        errors.append(f"只有 {n} 列，至少需要 {MIN_ROWS} 列")
    return n, errors


def publish_dataset(staged_path, key):
    """把已清洗的 CSV 發佈成 data/<filename>。回傳 {ok, dataset, path, rows, backup, error, warning}。"""
    d = DATASETS[key]
    res = {"ok": False, "dataset": key, "label": d["label"], "path": f"data/{d['filename']}", "rows": 0,
           "backup": None, "error": None, "warning": None}
    n, errors = validate_dataset_csv(staged_path, key)
    res["rows"] = n
    if errors:
        res["error"] = "資料集驗證失敗：" + "；".join(errors)
        return res
    target = os.path.join(_data_dir(), d["filename"])
    backup = None
    old_rows = None
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8-sig", newline="") as f:
            old_rows = max(0, sum(1 for _ in f) - 1)
        bdir = os.path.join(_data_dir(), "backup")
        os.makedirs(bdir, exist_ok=True)
        backup = os.path.join(bdir, f"{d['filename']}.{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        shutil.copy2(target, backup)
        olds = sorted(p for p in os.listdir(bdir) if p.startswith(d["filename"] + "."))
        for p in olds[:-KEEP_BACKUPS]:
            os.remove(os.path.join(bdir, p))
        res["backup"] = os.path.relpath(backup, project_root())
    if old_rows and n < 0.5 * old_rows:
        res["warning"] = f"新檔只有 {n} 列，不到舊檔 {old_rows} 列的一半，請確認不是不完整的匯出（舊檔已備份）"
    os.replace(staged_path, target)
    try:
        mod, fn = d["loader"]
        _, source = getattr(_module(mod), fn)()
        loaded = str(source).startswith("data/")
        err = None if loaded else f"載入函式沒有採用新檔（來源：{source}），可能是欄位值不符該資料集的額外檢查"
    except Exception as e:     # noqa: BLE001
        loaded, err = False, f"載入新檔時發生錯誤：{e}"
    if not loaded:
        if backup:
            shutil.copy2(backup, target)
        else:
            os.remove(target)
        res["error"] = err + "；已還原為發佈前的狀態"
        return res
    res["ok"] = True
    return res


def _run(name, fn, **kw):
    try:
        r = getattr(_module(name), fn)(**kw)
        return {"skill": name, "ok": True, "found": r.get("found", True), "guardrail_status": r.get("guardrail_status", r.get("status")),
                "answer_text": r.get("answer_text"), "steps": r.get("steps", []), "raw": r}
    except Exception as e:     # noqa: BLE001
        return {"skill": name, "ok": False, "found": False, "guardrail_status": "ERROR", "answer_text": f"執行失敗：{e}", "steps": [], "raw": {}}


def refresh_dataset(key):
    """重跑該資料集相關的 Skill（各 Skill 會自行把結果存成 data/*.json）。回傳結果清單（含 steps）。"""
    out = []
    if key == "sensor_history":
        s3 = _module("skill_03_sensor_data_preprocessing")
        rows, _ = s3.load_reference_dataset()
        mean_row = {f: round(sum(r[f] for r in rows) / len(rows), 4) for f in s3.FEATURES}   # 以資料集平均值當代表樣本
        out += [_run("skill_03_sensor_data_preprocessing", "preprocess_sensor_data", raw_values=mean_row),
                _run("skill_04_equipment_rul_prediction", "predict_equipment_rul"),
                _run("skill_05_degradation_feature_attribution", "attribute_degradation_features")]
    elif key == "failure_history":
        r6 = _run("skill_06_failure_probability_calc", "calculate_failure_probability")
        out.append(r6)
        out.append(_run("skill_07_risk_level_classification", "classify_risk_level",
                        failure_probability=r6["raw"].get("failure_probability")))
        out.append(_run("skill_08_cost_sensitive_threshold_tuning", "tune_cost_threshold"))
    elif key in ("process_quality", "batches"):
        out += [_run("skill_14_yield_rate_anomaly_detection", "detect_yield_anomaly"),
                _run("skill_15_feature_importance_ranking", "rank_feature_importance"),
                _run("skill_16_root_cause_attribution_report", "build_root_cause_report")]
    elif key == "steel_defects":
        out += [_run("skill_17_steel_surface_defect_classify", "classify_steel_defect"),
                _run("skill_18_defect_geometric_feature_eval", "evaluate_defect_features"),
                _run("skill_19_decision_tree_rule_extraction", "extract_decision_tree_rules")]
    elif key == "process_params":
        sp = _module("_spc_data")
        rows, _ = sp.load_data()
        Z, _ = sp.standardize(rows, sp.COLUMNS)
        out += [_run("skill_21_elbow_method_optimal_k", "find_optimal_k", data=Z, max_k=8)]
        k = out[-1]["raw"].get("optimal_k") or 3
        out += [_run("skill_20_process_parameter_kmeans", "run_kmeans", z_scores=Z, k=k),
                _run("skill_22_spc_control_limit_monitoring", "monitor_spc", data_series=[z[0] for z in Z])]
    elif key == "ipi_monthly":
        out += [_run("skill_23_ipi_mlp_forecast", "forecast_ipi_mlp")]
    elif key == "equipment_risk":
        eq = _module("_equipment_data")
        rows, _ = eq.load_data()
        Z, _ = eq.risk_matrix(rows, eq.INDICATORS)
        h = _run("skill_24_preventive_maintenance_hierarchy", "build_hierarchy", equipment_risk_matrix=Z, linkage="average",
                 equipment_ids=[r["equipment_id"] for r in rows])
        out.append(h)
        if h["raw"].get("found"):
            out.append(_run("skill_25_factory_risk_dendrogram_eval", "evaluate_dendrogram", hierarchy=h["raw"], equipment_rows=rows))
    return out
