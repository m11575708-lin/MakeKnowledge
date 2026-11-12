"""
_repair_data.py - skill_09 / skill_10 / skill_11 共用的維修案例庫

資料來源：
  1. 優先讀取 data/repair_cases.json（請放入真實歷史維修工單）：
     {"cases": [{"case_id","equipment_id","date","error_code","pattern"(可省略),"pattern_label"(可省略),
                 "description","steps":[...],"features":[振動,溫度,壓力] 或 {"vibration","temperature","pressure"},
                 "parts_used":["SP-xxxx",...]}],
      "parts": [{"part_id","name","stock","safety_stock"}]}
  2. 不存在或格式錯誤時，使用下方「示範資料」(16 筆案例、10 項備品)。
     示範資料是手寫的範例，不是真實工單，也不是真實庫存。

特徵向量順序固定為：[vibration 振動 mm/s, temperature 溫度 °C, pressure 壓力 MPa]
"""

import json
import math
import os

try:
    from ._common import default_output_path
except ImportError:
    from _common import default_output_path

FEATURES = ["vibration", "temperature", "pressure"]
FEATURE_LABELS = {"vibration": "振動值", "temperature": "運轉溫度", "pressure": "運轉壓力"}
FEATURE_UNITS = {"vibration": "mm/s", "temperature": "°C", "pressure": "MPa"}
HARD_LIMITS = {"vibration": (0.0, 100.0), "temperature": (-50.0, 500.0), "pressure": (0.0, 30.0)}

ERROR_CODE_PATTERN = r"^E-\d{4}$"


def clean_num(v):
    """JSON 安全：非有限數值或非數值回傳 None。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _case(case_id, equipment_id, date, code, pattern, label, desc, steps, feats, parts):
    return {"case_id": case_id, "equipment_id": equipment_id, "date": date, "error_code": code,
            "pattern": pattern, "pattern_label": label, "description": desc, "steps": steps,
            "features": feats, "parts_used": parts}


_OH, _OHL = "MOTOR_OVERHEAT", "馬達過熱"
_BW, _BWL = "BEARING_WEAR", "軸承磨損"
_HP, _HPL = "HYDRAULIC_PRESSURE_LOSS", "液壓壓力流失"
_CB, _CBL = "CLUTCH_BRAKE_FAULT", "離合器／煞車異常"

DEMO_CASES = [
    _case("MA-2024-089", "EQ-PRESS-01", "2024-03-12", "E-8021", _OH, _OHL,
          "主馬達運轉溫度持續超過 75°C，伴隨輕微異常振動，冷卻風扇轉速不足。",
          ["切斷電源並掛牌上鎖", "拆檢冷卻風扇與風道並清除積塵", "檢查並更換馬達軸承、補充潤滑油脂", "更換溫度感測器，試運轉 30 分鐘確認溫升"],
          [2.8, 75.0, 1.8], ["SP-8821", "SP-8822", "SP-8850"]),
    _case("MA-2024-102", "EQ-SHEAR-02", "2024-05-03", "E-8021", _OH, _OHL,
          "剪切機主馬達過熱跳脫，冷卻水流量偏低。",
          ["停機降溫並讀取跳脫紀錄", "清洗冷卻水路過濾網", "更換冷卻風扇總成", "復歸後連續監測溫度 1 小時"],
          [3.1, 79.0, 1.7], ["SP-8822", "SP-8823"]),
    _case("MA-2024-117", "EQ-PRESS-01", "2024-06-21", "E-8021", _OH, _OHL,
          "馬達溫度緩慢上升，軸承潤滑不良。",
          ["停機並量測軸承座溫度", "更換馬達軸承", "重新注入潤滑油脂", "試運轉並記錄振動值"],
          [2.6, 72.0, 1.9], ["SP-8821", "SP-8850"]),
    _case("MA-2024-133", "EQ-LIFT-03", "2024-08-14", "E-8021", _OH, _OHL,
          "升降機馬達過熱，溫度感測值飄移。",
          ["切斷電源並確認負載狀態", "以標準溫度計比對感測器讀值", "更換溫度感測器與冷卻風扇", "檢查軸承並補充油脂後試運轉"],
          [3.4, 83.0, 1.6], ["SP-8823", "SP-8822", "SP-8821"]),

    _case("MA-2024-041", "EQ-PRESS-01", "2024-02-05", "E-8032", _BW, _BWL,
          "主軸振動值偏高，運轉時有金屬摩擦聲。",
          ["停機並以振動計量測各軸承座", "拆卸主軸軸承並檢查滾道磨損", "更換軸承與聯軸器", "加注潤滑油脂並試運轉確認振動值"],
          [4.6, 64.0, 1.8], ["SP-8821", "SP-8850", "SP-8851"]),
    _case("MA-2024-058", "EQ-SHEAR-02", "2024-04-02", "E-8032", _BW, _BWL,
          "剪切機傳動端振動明顯，軸承溫度略高。",
          ["停機並確認軸承異音位置", "更換傳動端軸承", "檢查聯軸器同心度並更換", "試運轉 1 小時記錄振動趨勢"],
          [5.2, 68.0, 1.9], ["SP-8821", "SP-8851"]),
    _case("MA-2024-076", "EQ-LIFT-03", "2024-04-29", "E-8032", _BW, _BWL,
          "升降機驅動軸振動超標，潤滑油脂乾涸。",
          ["停機並清除舊油脂", "更換驅動軸軸承", "重新注入潤滑油脂", "試運轉並記錄振動值"],
          [4.1, 61.0, 1.7], ["SP-8821", "SP-8850"]),
    _case("MA-2024-125", "EQ-PRESS-01", "2024-07-30", "E-8032", _BW, _BWL,
          "衝壓機曲軸軸承嚴重磨損，振動持續惡化。",
          ["立即停機並隔離設備", "拆解曲軸並檢查軸頸", "更換軸承與聯軸器並補充油脂", "對心校正後試運轉並設定追蹤檢點"],
          [5.5, 70.0, 2.0], ["SP-8821", "SP-8851", "SP-8850"]),

    _case("MA-2024-063", "EQ-PRESS-01", "2024-03-01", "E-7015", _HP, _HPL,
          "液壓系統壓力無法建立，油缸出力不足。",
          ["洩壓並確認油位", "檢查油缸密封環並更換", "補充液壓油並排氣", "加壓測試確認壓力維持"],
          [1.8, 60.0, 0.9], ["SP-8830", "SP-8832"]),
    _case("MA-2024-081", "EQ-SHEAR-02", "2024-04-18", "E-7015", _HP, _HPL,
          "壓力表讀值偏低且波動，管路接頭滲油。",
          ["洩壓並鎖緊管路接頭", "更換壓力感測器", "更換密封環組並補充液壓油", "加壓測試 15 分鐘無洩漏"],
          [2.0, 66.0, 1.1], ["SP-8830", "SP-8831", "SP-8832"]),
    _case("MA-2024-094", "EQ-LIFT-03", "2024-05-27", "E-7015", _HP, _HPL,
          "升降機升力不足，壓力讀值異常偏低。",
          ["確認壓力感測器訊號", "以標準壓力計比對後更換感測器", "更換老化液壓油", "加壓測試確認升降動作"],
          [1.6, 57.0, 0.8], ["SP-8831", "SP-8832"]),
    _case("MA-2024-140", "EQ-PRESS-01", "2024-09-09", "E-7015", _HP, _HPL,
          "液壓缸緩慢內洩，保壓能力下降。",
          ["洩壓並拆檢油缸", "更換密封環組", "補充液壓油並排氣", "保壓測試 30 分鐘"],
          [2.2, 68.0, 1.2], ["SP-8830", "SP-8832"]),

    _case("MA-2024-052", "EQ-PRESS-01", "2024-02-20", "E-6040", _CB, _CBL,
          "離合器結合延遲，煞車停止距離變長。",
          ["停機並確認安全裝置", "檢查離合器摩擦片厚度", "更換摩擦片組與煞車線圈", "測試停止時間符合規範"],
          [3.2, 69.0, 2.6], ["SP-8840", "SP-8841"]),
    _case("MA-2024-088", "EQ-PRESS-01", "2024-05-15", "E-6040", _CB, _CBL,
          "離合器過熱並有焦味，滑差明顯。",
          ["停機降溫並隔離設備", "更換離合器摩擦片組", "更換煞車線圈並補充潤滑油脂", "測試停止時間與滑差"],
          [3.6, 73.0, 2.8], ["SP-8840", "SP-8841", "SP-8850"]),
    _case("MA-2024-110", "EQ-SHEAR-02", "2024-06-30", "E-6040", _CB, _CBL,
          "煞車釋放不完全，運轉時拖滯發熱。",
          ["停機並檢查煞車間隙", "更換煞車線圈", "更換摩擦片組並調整間隙", "試運轉確認釋放正常"],
          [2.9, 66.0, 2.4], ["SP-8841", "SP-8840"]),
    _case("MA-2024-128", "EQ-SHEAR-02", "2024-08-22", "E-6040", _CB, _CBL,
          "離合器壓力偏高，結合時衝擊明顯。",
          ["停機並洩除氣壓", "更換離合器摩擦片組", "潤滑傳動部位並調整氣壓", "試運轉確認結合平順"],
          [3.4, 71.0, 2.9], ["SP-8840", "SP-8850"]),
]

DEMO_PARTS = [
    {"part_id": "SP-8821", "name": "馬達軸承 6309", "stock": 6, "safety_stock": 4},
    {"part_id": "SP-8822", "name": "冷卻風扇總成", "stock": 2, "safety_stock": 3},
    {"part_id": "SP-8823", "name": "溫度感測器 PT100", "stock": 12, "safety_stock": 5},
    {"part_id": "SP-8830", "name": "液壓密封環組", "stock": 0, "safety_stock": 2},
    {"part_id": "SP-8831", "name": "壓力感測器 0-10MPa", "stock": 5, "safety_stock": 2},
    {"part_id": "SP-8832", "name": "液壓油 46# 20L", "stock": 9, "safety_stock": 4},
    {"part_id": "SP-8840", "name": "離合器摩擦片組", "stock": 3, "safety_stock": 2},
    {"part_id": "SP-8841", "name": "煞車線圈", "stock": 1, "safety_stock": 2},
    {"part_id": "SP-8850", "name": "潤滑油脂 EP2 1kg", "stock": 20, "safety_stock": 6},
    {"part_id": "SP-8851", "name": "聯軸器", "stock": 4, "safety_stock": 2},
]


def stock_status(part: dict) -> str:
    """OUT：缺料；LOW：庫存不高於安全庫存；NORMAL：正常。"""
    stock, safety = part.get("stock", 0), part.get("safety_stock", 0)
    if stock <= 0:
        return "OUT"
    return "LOW" if stock <= safety else "NORMAL"


def _normalize_case(c: dict):
    feats = c.get("features")
    if isinstance(feats, dict):
        feats = [feats.get(f) for f in FEATURES]
    if (not isinstance(feats, (list, tuple)) or len(feats) != len(FEATURES)
            or any(clean_num(v) is None for v in feats)):
        raise ValueError(f"案例 {c.get('case_id')} 的 features 必須是 {len(FEATURES)} 個有限數值")
    steps = c.get("steps") or []
    parts = c.get("parts_used") or []
    if not isinstance(steps, list) or not isinstance(parts, list):
        raise ValueError(f"案例 {c.get('case_id')} 的 steps / parts_used 必須是陣列")
    code = str(c["error_code"])
    return {
        "case_id": str(c["case_id"]), "equipment_id": str(c.get("equipment_id", "")),
        "date": str(c.get("date", "")), "error_code": code,
        "pattern": str(c.get("pattern") or code), "pattern_label": str(c.get("pattern_label") or c.get("pattern") or code),
        "description": str(c.get("description", "")), "steps": [str(s) for s in steps],
        "features": [float(v) for v in feats], "parts_used": sorted({str(p) for p in parts}),
    }


def load_case_base(json_path: str = None) -> dict:
    """回傳 {"cases","parts","source"}。JSON 讀取失敗時退回示範資料。"""
    path = json_path or default_output_path("repair_cases.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cases = [_normalize_case(c) for c in raw["cases"]]
            parts = [{"part_id": str(p["part_id"]), "name": str(p["name"]),
                      "stock": int(p["stock"]), "safety_stock": int(p.get("safety_stock", 0))}
                     for p in raw.get("parts", [])]
            ids = [c["case_id"] for c in cases]
            if len(cases) < 5:
                raise ValueError(f"案例僅 {len(cases)} 筆，至少需要 5 筆")
            if len(ids) != len(set(ids)):
                raise ValueError("case_id 不可重複")
            return {"cases": cases, "parts": parts, "source": "data/repair_cases.json"}
        except Exception as e:
            print(f"讀取 repair_cases.json 失敗：{e}，改用示範資料", flush=True)
    return {"cases": [_normalize_case(c) for c in DEMO_CASES], "parts": [dict(p) for p in DEMO_PARTS],
            "source": "demo_cases (示範資料，非真實工單)"}


def validate_vector(raw):
    """接受 list/tuple（依 FEATURES 順序）或 dict；回傳 (list | None, errors)。"""
    if isinstance(raw, dict):
        raw = [raw.get(f) for f in FEATURES]
    if not isinstance(raw, (list, tuple)):
        return None, ["feature_vector 必須是陣列或物件"]
    if len(raw) != len(FEATURES):
        return None, [f"feature_vector 需要 {len(FEATURES)} 個數值（{', '.join(FEATURES)}），收到 {len(raw)} 個"]
    out, errors = [], []
    for f, v in zip(FEATURES, raw):
        label = FEATURE_LABELS[f]
        if v is None:
            errors.append(f"缺少 {label}")
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{label} 必須為數值")
        elif not math.isfinite(v):
            errors.append(f"{label} 不可為 NaN 或無限大")
        elif not HARD_LIMITS[f][0] <= v <= HARD_LIMITS[f][1]:
            errors.append(f"{label} = {v:g} 超出合理範圍 [{HARD_LIMITS[f][0]:g}, {HARD_LIMITS[f][1]:g}] {FEATURE_UNITS[f]}")
        else:
            out.append(float(v))
    return (out if not errors else None), errors


def feature_stats(cases: list) -> list:
    """每個特徵的 (mean, std(樣本), min, max)。std 為 0 時丟出 ValueError。"""
    stats = []
    for i, f in enumerate(FEATURES):
        vals = [c["features"][i] for c in cases]
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
        if std <= 0:
            raise ValueError(f"案例庫中特徵 {f} 的標準差為 0，無法標準化")
        stats.append({"mean": mean, "std": std, "min": min(vals), "max": max(vals)})
    return stats


def validate_weights(weights):
    """None -> 全部 1；否則需為 3 個正的有限數值，正規化為平均 1。回傳 (list | None, errors)。"""
    if weights is None:
        return [1.0] * len(FEATURES), []
    if isinstance(weights, dict):
        weights = [weights.get(f) for f in FEATURES]
    if not isinstance(weights, (list, tuple)) or len(weights) != len(FEATURES):
        return None, [f"weights 必須是 {len(FEATURES)} 個數值"]
    if any(isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0 for w in weights):
        return None, ["weights 必須是非負的有限數值"]
    total = sum(weights)
    if total <= 0:
        return None, ["weights 不可全為 0"]
    return [w * len(FEATURES) / total for w in weights], []
