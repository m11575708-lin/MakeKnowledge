"""
_equipment_data.py - page13 設備風險指標資料（skill_24 / 25 與 /api/index-forecast 共用）

指標：failure_rate 故障率 (次/千小時，越高越危險)、mtbf_hours 平均故障間隔 (小時，越高越安全)、
      load_pct 運轉負載 (%，越高越危險)。
風險方向：mtbf 取負號，使「數值越大＝風險越高」三個指標方向一致，再做 z 分數標準化。

資料來源（依序）：
  1. data/equipment_risk.csv   欄位 equipment_id,zone,failure_rate,mtbf_hours,load_pct
  2. 不存在時使用固定 seed 的示範資料：18 台設備（衝壓區／軋延區／加熱區各 6 台），
     三區的風險水準由我設定（衝壓區偏高）並加入重疊與 1 台離群設備。這是假想資料，不是真實產線紀錄。
"""

import csv
import math
import os
import random

try:
    from ._common import default_output_path
except ImportError:
    from _common import default_output_path

INDICATORS = ["failure_rate", "mtbf_hours", "load_pct"]
LABELS = {"failure_rate": "故障率", "mtbf_hours": "MTBF", "load_pct": "運轉負載"}
UNITS = {"failure_rate": "次/千小時", "mtbf_hours": "小時", "load_pct": "%"}
DIRECTION = {"failure_rate": 1.0, "mtbf_hours": -1.0, "load_pct": 1.0}
MIN_ITEMS = 5
MAX_ITEMS = 150


def clean_num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def generate_demo(seed: int = 24):
    rng = random.Random(seed)
    spec = {   # 區：(故障率 μ,σ)、(MTBF μ,σ)、(負載 μ,σ)
        "衝壓區": ((4.2, 0.7), (520, 90), (88, 5)),
        "軋延區": ((2.4, 0.5), (1100, 160), (76, 6)),
        "加熱區": ((0.9, 0.3), (2300, 300), (62, 6)),
    }
    rows = []
    for zone, (f, m, l) in spec.items():
        code = {"衝壓區": "PRESS", "軋延區": "ROLL", "加熱區": "HEAT"}[zone]
        for i in range(6):
            rows.append({"equipment_id": f"EQ-{code}-{i + 1:02d}", "zone": zone,
                         "failure_rate": round(max(0.1, rng.gauss(*f)), 2),
                         "mtbf_hours": round(max(50.0, rng.gauss(*m)), 0),
                         "load_pct": round(min(100.0, max(10.0, rng.gauss(*l))), 1)})
    rows[10].update({"failure_rate": 3.6, "mtbf_hours": 700.0, "load_pct": 90.0})   # 一台軋延區設備狀況接近衝壓區
    return rows


def load_data():
    path = default_output_path("equipment_risk.csv")
    if os.path.exists(path):
        try:
            rows = []
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                need = ["equipment_id", "zone"] + INDICATORS
                if not reader.fieldnames or not set(need) <= set(reader.fieldnames):
                    raise ValueError(f"CSV 欄位需包含 {need}")
                for rec in reader:
                    row = {"equipment_id": rec["equipment_id"].strip(), "zone": rec["zone"].strip()}
                    for k in INDICATORS:
                        row[k] = float(rec[k])
                        if not math.isfinite(row[k]):
                            raise ValueError("指標必須是有限數字")
                    if not row["equipment_id"]:
                        raise ValueError("equipment_id 不可為空")
                    rows.append(row)
            if len({r["equipment_id"] for r in rows}) != len(rows):
                raise ValueError("equipment_id 不可重複")
            if not MIN_ITEMS <= len(rows) <= MAX_ITEMS:
                raise ValueError(f"設備數需介於 {MIN_ITEMS}–{MAX_ITEMS}，目前 {len(rows)}")
            return rows, "data/equipment_risk.csv"
        except Exception as e:
            print(f"讀取 equipment_risk.csv 失敗：{e}，改用示範資料", flush=True)
    return generate_demo(), "synthetic_demo (seed=24，示範設備資料非真實產線紀錄)"


def risk_matrix(rows, indicators):
    """回傳 (風險方向 z 分數矩陣, stats)；某指標標準差為 0 會拋出 ValueError。"""
    stats = {}
    for k in indicators:
        vals = [r[k] * DIRECTION[k] for r in rows]
        m = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
        if sd <= 0:
            raise ValueError(f"{LABELS[k]} 所有設備數值相同，無法標準化")
        stats[k] = {"mean": m, "std": sd}
    Z = [[(r[k] * DIRECTION[k] - stats[k]["mean"]) / stats[k]["std"] for k in indicators] for r in rows]
    return Z, stats
