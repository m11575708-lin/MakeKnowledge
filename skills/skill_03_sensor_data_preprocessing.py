"""
skill_03_sensor_data_preprocessing.py - 感測器數據 Z-Score 標準化技能

對應系統規格：US-03 / 06. 設備壽命預測頁
演算法機制：參考資料載入 -> 輸入邊界防呆 -> 平均數/標準差 -> Z-Score 轉換 -> 外插 Guardrail

參考資料來源：
  1. 優先讀取 data/sensor_history.csv
     欄位：operating_hours,vibration,temperature,load_rate,rul_hours
  2. 若不存在，使用 generate_reference_dataset() 產生「固定 seed 的示範合成資料」。
     這是為了讓系統在沒有真實資料時也能完整運行，並非真實設備紀錄；
     正式使用時請放入真實歷史資料。
"""

import csv
import json
import math
import os
import random
import statistics

try:
    from ._common import StepLog, default_output_path, save_json
except ImportError:
    from _common import StepLog, default_output_path, save_json

SKILL_NAME = "skill_03_sensor_data_preprocessing"

FEATURES = ["operating_hours", "vibration", "temperature", "load_rate"]
FEATURE_LABELS = {
    "operating_hours": "累積運轉時數",
    "vibration": "設備振動值",
    "temperature": "運轉溫度",
    "load_rate": "負載率",
}
FEATURE_UNITS = {"operating_hours": "h", "vibration": "mm/s", "temperature": "°C", "load_rate": "%"}

# 物理合理範圍（超出直接攔截，視為輸入錯誤）
HARD_LIMITS = {
    "operating_hours": (0.0, 100000.0),
    "vibration": (0.0, 100.0),
    "temperature": (-50.0, 500.0),
    "load_rate": (0.0, 150.0),
}
BLOCK_Z = 4.0   # |z| 超過此值視為嚴重外插，拒絕預測
WARN_Z = 3.0

PLAN = [
    ("載入參考資料集", "Dataset Loader", "csv, random"),
    ("輸入邊界與型別防呆", "Boundary & Type Validation", "math"),
    ("計算特徵平均數與標準差", "Sample Mean / Standard Deviation", "statistics"),
    ("Z-Score 標準化轉換", "Z-Score Standardization (StandardScaler)", "Python Built-in"),
    ("外插 Guardrail 檢核與結果輸出", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]

# 示範合成資料的「真實」生成式（單位：原始單位）。僅用於 demo 資料。
_DEMO_TRUE = {"intercept": 1020.0, "operating_hours": -0.20, "vibration": -30.0,
              "temperature": -2.5, "load_rate": -1.5}


def generate_reference_dataset(n: int = 200, seed: int = 42, noise_sd: float = 10.0) -> list:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        row = {
            "operating_hours": rng.uniform(200, 2500),
            "vibration": rng.uniform(0.5, 5.0),
            "temperature": rng.uniform(45, 90),
            "load_rate": rng.uniform(50, 95),
        }
        rul = _DEMO_TRUE["intercept"] + sum(_DEMO_TRUE[f] * row[f] for f in FEATURES) + rng.gauss(0, noise_sd)
        row["rul_hours"] = max(0.0, rul)
        rows.append(row)
    return rows


def load_reference_dataset(csv_path: str = None):
    """回傳 (rows, source_label)。CSV 讀取失敗時退回示範資料，並在標籤中註明。"""
    path = csv_path or default_output_path("sensor_history.csv")
    if os.path.exists(path):
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                needed = FEATURES + ["rul_hours"]
                if not reader.fieldnames or not set(needed) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {needed}")
                for rec in reader:
                    rows.append({k: float(rec[k]) for k in needed})
            if len(rows) < 20:
                raise ValueError(f"資料僅 {len(rows)} 筆，至少需要 20 筆")
            return rows, "data/sensor_history.csv"
        except Exception as e:
            print(f"讀取 sensor_history.csv 失敗：{e}，改用示範合成資料", flush=True)
    return generate_reference_dataset(), "synthetic_demo (seed=42)"


def compute_zscore_stats(rows: list) -> dict:
    stats = {}
    for f in FEATURES:
        vals = [r[f] for r in rows]
        std = statistics.stdev(vals)
        if std <= 0:
            raise ValueError(f"特徵 {f} 標準差為 0，無法標準化")
        stats[f] = {"mean": statistics.mean(vals), "std": std, "min": min(vals), "max": max(vals)}
    return stats


def validate_sensor_inputs(raw):
    """接受 dict 或依 FEATURES 順序的 list；回傳 (values_dict | None, errors)。"""
    if isinstance(raw, (list, tuple)):
        if len(raw) != len(FEATURES):
            return None, [f"需要 {len(FEATURES)} 個數值（{', '.join(FEATURES)}），收到 {len(raw)} 個"]
        raw = dict(zip(FEATURES, raw))
    if not isinstance(raw, dict):
        return None, ["輸入格式錯誤，需為 dict 或 list"]

    values, errors = {}, []
    for f in FEATURES:
        v = raw.get(f)
        if v is None:
            errors.append(f"缺少欄位 {f}")
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{FEATURE_LABELS[f]} 必須為數值")
            continue
        if not math.isfinite(v):
            errors.append(f"{FEATURE_LABELS[f]} 不可為 NaN 或無限大")
            continue
        lo, hi = HARD_LIMITS[f]
        if not lo <= v <= hi:
            errors.append(f"{FEATURE_LABELS[f]} = {v} 超出合理範圍 [{lo}, {hi}] {FEATURE_UNITS[f]}")
            continue
        values[f] = float(v)
    return (values if not errors else None), errors


def zscore_transform(values: dict, stats: dict) -> dict:
    return {f: (values[f] - stats[f]["mean"]) / stats[f]["std"] for f in FEATURES}


def check_extrapolation(values: dict, stats: dict):
    """回傳 (warnings, blocked_reasons)。"""
    warnings, blocked = [], []
    for f in FEATURES:
        s = stats[f]
        z = (values[f] - s["mean"]) / s["std"]
        label = f"{FEATURE_LABELS[f]}={values[f]:g}{FEATURE_UNITS[f]}"
        if abs(z) > BLOCK_Z:
            blocked.append(f"{label} 的 |z|={abs(z):.2f} > {BLOCK_Z}，遠離訓練資料範圍")
        elif values[f] < s["min"] or values[f] > s["max"]:
            warnings.append(f"{label} 超出訓練資料範圍 [{s['min']:.1f}, {s['max']:.1f}]，預測屬外插，可信度下降")
        elif abs(z) > WARN_Z:
            warnings.append(f"{label} 的 |z|={abs(z):.2f} > {WARN_Z}")
    return warnings, blocked


def _round_stats(stats: dict) -> dict:
    return {f: {k: round(v, 4) for k, v in s.items()} for f, s in stats.items()}


def preprocess_sensor_data(raw_values=None, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("sensor_preprocess_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    if raw_values is None or raw_values == [] or raw_values == {}:
        result = {
            "status": "success", "found": False, "raw_values": {}, "standardized_values": [],
            "standardized": {}, "warnings": [], "guardrail_status": "BLOCKED_BY_GUARDRAIL (empty input)",
            "answer_text": f"請提供感測器數值：{', '.join(FEATURES)}。", "steps": [],
        }
        save_json(result, out_path)
        return result

    # 1. 載入
    rows, source = load_reference_dataset()
    log.add(f"載入 {len(rows)} 筆參考資料（來源：{source}）作為標準化基準。")

    # 2. 驗證
    values, errors = validate_sensor_inputs(raw_values)
    base = {"status": "success", "data_source": source, "n_samples": len(rows), "feature_order": FEATURES}

    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        log.skip_to_last("輸入未通過驗證")
        guardrail = "BLOCKED_BY_GUARDRAIL (invalid input)"
        log.add(f"防呆檢核狀態：{guardrail}。")
        result = {**base, "found": False, "raw_values": raw_values if isinstance(raw_values, dict) else {},
                  "standardized_values": [], "standardized": {}, "warnings": errors,
                  "guardrail_status": guardrail, "answer_text": "輸入未通過驗證：" + "；".join(errors),
                  "steps": log.steps}
        save_json(result, out_path)
        return result
    log.add("4 個欄位皆為有限數值且位於物理合理範圍內。")

    # 3. 平均數 / 標準差
    stats = compute_zscore_stats(rows)
    log.add("以樣本標準差 (n-1) 計算各特徵統計量：" + "；".join(
        f"{f} μ={stats[f]['mean']:.2f}, σ={stats[f]['std']:.2f}" for f in FEATURES))

    # 4. Z-Score
    z = zscore_transform(values, stats)
    log.add("套用 z = (x - μ) / σ：" + "；".join(f"{f}={z[f]:+.3f}" for f in FEATURES))

    # 5. Guardrail
    warnings, blocked = check_extrapolation(values, stats)
    if blocked:
        guardrail = "BLOCKED_BY_GUARDRAIL (extrapolation)"
        log.add(f"防呆檢核狀態：{guardrail}。" + "；".join(blocked))
        found, answer = False, "輸入值遠離訓練資料範圍，已攔截：" + "；".join(blocked)
        warnings = blocked + warnings
    else:
        guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
        log.add(f"防呆檢核狀態：{guardrail}。" + ("；".join(warnings) if warnings else "所有數值皆在訓練範圍內。"))
        found = True
        answer = "已完成 Z-Score 標準化：" + "，".join(f"{FEATURE_LABELS[f]} z={z[f]:+.2f}" for f in FEATURES) + "。"

    result = {
        **base, "found": found, "raw_values": values,
        "standardized_values": [round(z[f], 4) for f in FEATURES],
        "standardized": {f: round(z[f], 4) for f in FEATURES},
        "reference_stats": _round_stats(stats),
        "warnings": warnings, "guardrail_status": guardrail,
        "answer_text": answer, "steps": log.steps,
    }
    save_json(result, out_path)
    return result


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_03_sensor_data_preprocessing ===")
    print(json.dumps(preprocess_sensor_data([1500, 2.8, 75.0, 85.0]), ensure_ascii=False, indent=2))
