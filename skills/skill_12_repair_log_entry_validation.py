"""
skill_12_repair_log_entry_validation.py - 維修履歷欄位正則與臨界值防呆技能

對應系統規格：US-08 / 09. 維修案例登錄與故障碼驗證頁
演算法機制：欄位存在與型別檢查 -> 正則表達式格式驗證 -> 臨界值（硬上下限）邊界檢查
            -> 跨欄位邏輯與常態範圍檢查 -> 彙整判定與正規化輸出

與 skill_02~11 不同：本技能「不中途停止」，會把所有欄位的錯誤一次列出，方便使用者一次改完。
只有電流 current_a 與壓力 pressure_mpa 是必填；設備 ID、日期時間、故障碼、處置說明若有提供才會檢查
（所以規格範例 {"current_a": 45.2, "pressure_mpa": 2.1} 可單獨呼叫）。

臨界值說明：
  HARD_LIMITS 為物理上不可能的範圍，超出即判定輸入錯誤（is_valid=False）。
  SOFT_LIMITS 為常態運轉範圍的「示範值」，超出只給警告、不擋儲存；請依設備銘牌調整。
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone

try:
    from ._common import StepLog, default_output_path, save_json
    from ._repair_data import ERROR_CODE_PATTERN, clean_num, load_case_base
except ImportError:
    from _common import StepLog, default_output_path, save_json
    from _repair_data import ERROR_CODE_PATTERN, clean_num, load_case_base

SKILL_NAME = "skill_12_repair_log_entry_validation"

EQUIPMENT_ID_PATTERN = r"^EQ-[A-Z]{2,10}-\d{2,3}$"
DATETIME_MIN = datetime(2000, 1, 1)
FUTURE_TOLERANCE = timedelta(hours=24)   # 容許瀏覽器與伺服器的時區差
DESC_MIN, DESC_MAX = 10, 500

HARD_LIMITS = {"current_a": (0.0, 500.0), "pressure_mpa": (0.0, 30.0)}
SOFT_LIMITS = {"current_a": (5.0, 80.0), "pressure_mpa": (0.5, 3.2)}
LABELS = {"current_a": "即時電流", "pressure_mpa": "即時壓力", "equipment_id": "設備 ID",
          "repair_datetime": "維修日期時間", "error_code": "故障碼", "description": "處置說明"}
UNITS = {"current_a": "A", "pressure_mpa": "MPa"}

PLAN = [
    ("欄位存在與型別檢查", "Presence & Type Validation", "math"),
    ("正則表達式格式驗證", "Regular Expression Format Validation", "re, datetime"),
    ("臨界值硬上下限邊界檢查", "Boundary Value Check (Hard Limits)", "math"),
    ("跨欄位邏輯與常態範圍檢查", "Cross-field Consistency & Soft-limit Check", "Python Control Flow"),
    ("驗證結果彙整與正規化輸出", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]


def _parse_datetime(text: str):
    """接受 ISO 8601（含 datetime-local 的 YYYY-MM-DDTHH:MM）；含時區者轉為本機無時區時間。"""
    dt = datetime.fromisoformat(text.strip())
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def validate_repair_log_entry(
    current_a=None, pressure_mpa=None, equipment_id=None, repair_datetime=None,
    error_code=None, description=None, output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("repair_log_validation_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    fields = []   # {"field","label","ok","message"}
    warnings = []

    def ok(field, message="通過"):
        fields.append({"field": field, "label": LABELS[field], "ok": True, "message": message})

    def bad(field, message):
        fields.append({"field": field, "label": LABELS[field], "ok": False, "message": message})

    # 1. 存在與型別
    numeric = {}
    for name, v in (("current_a", current_a), ("pressure_mpa", pressure_mpa)):
        if v is None:
            bad(name, "必填欄位未提供")
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            bad(name, "必須為數值")
        elif not math.isfinite(v):
            bad(name, "不可為 NaN 或無限大")
        else:
            numeric[name] = float(v)
    text_fields = {}
    for name, v in (("equipment_id", equipment_id), ("repair_datetime", repair_datetime),
                    ("error_code", error_code), ("description", description)):
        if v is None:
            continue
        if not isinstance(v, str):
            bad(name, "必須為文字")
        elif not v.strip():
            bad(name, "不可為空白")
        else:
            text_fields[name] = v
    n_type_err = sum(1 for f in fields if not f["ok"])
    log.add(f"必填數值欄位 2 項（電流、壓力），選填文字欄位提供 {len(text_fields)} 項；型別與存在檢查發現 {n_type_err} 項問題。")

    # 2. 正則 / 格式
    normalized = {}
    if "equipment_id" in text_fields:
        v = text_fields["equipment_id"].strip().upper()
        if re.match(EQUIPMENT_ID_PATTERN, v):
            ok("equipment_id", f"格式正確（{v}）"); normalized["equipment_id"] = v
        else:
            bad("equipment_id", "格式需為 EQ-類別-編號，例如 EQ-PRESS-01")
    if "error_code" in text_fields:
        v = text_fields["error_code"].strip().upper()
        if re.match(ERROR_CODE_PATTERN, v):
            known = sorted({c["error_code"] for c in load_case_base()["cases"]})
            if v in known:
                ok("error_code", f"格式正確且為已收錄故障碼（{v}）")
            else:
                ok("error_code", f"格式正確（{v}），但案例庫尚未收錄此故障碼")
                warnings.append(f"故障碼 {v} 尚未收錄於案例庫（已收錄：{'、'.join(known)}），儲存後將成為新故障碼")
            normalized["error_code"] = v
        else:
            bad("error_code", "格式需為 E- 加 4 位數字，例如 E-8021")
    if "repair_datetime" in text_fields:
        try:
            dt = _parse_datetime(text_fields["repair_datetime"])
            if dt < DATETIME_MIN:
                bad("repair_datetime", f"不可早於 {DATETIME_MIN:%Y-%m-%d}")
            elif dt > datetime.now() + FUTURE_TOLERANCE:
                bad("repair_datetime", "不可是未來時間")
            else:
                ok("repair_datetime", f"格式正確（{dt:%Y-%m-%d %H:%M}）")
                normalized["repair_datetime"] = dt.strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            bad("repair_datetime", "日期時間格式錯誤，需為 YYYY-MM-DD HH:MM")
    if "description" in text_fields:
        v = re.sub(r"\s+", " ", text_fields["description"]).strip()
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text_fields["description"]):
            bad("description", "含有不可顯示的控制字元")
        elif not DESC_MIN <= len(v) <= DESC_MAX:
            bad("description", f"長度需介於 {DESC_MIN} 到 {DESC_MAX} 字（目前 {len(v)} 字）")
        elif not re.search(r"[一-鿿A-Za-z]{4,}", v):
            bad("description", "內容需包含文字描述，不能只有數字或符號")
        else:
            ok("description", f"長度 {len(v)} 字")
            normalized["description"] = v
    n_fmt = sum(1 for f in fields if f["field"] in text_fields)
    n_fmt_bad = sum(1 for f in fields if f["field"] in text_fields and not f["ok"])
    log.add(f"以正則與解析驗證設備 ID（{EQUIPMENT_ID_PATTERN}）、故障碼（{ERROR_CODE_PATTERN}）、ISO 日期時間與處置說明文字，"
            f"共檢查 {n_fmt} 項，{n_fmt_bad} 項不合格。")

    # 3. 臨界值硬上下限
    for name, v in numeric.items():
        lo, hi = HARD_LIMITS[name]
        if lo <= v <= hi:
            ok(name, f"{v:g} {UNITS[name]} 在合理範圍 [{lo:g}, {hi:g}] 內")
            normalized[name] = v
        else:
            bad(name, f"{v:g} {UNITS[name]} 超出物理合理範圍 [{lo:g}, {hi:g}]")
    log.add("硬上下限：" + "；".join(f"{LABELS[k]} [{HARD_LIMITS[k][0]:g}, {HARD_LIMITS[k][1]:g}] {UNITS[k]}" for k in HARD_LIMITS)
            + f"。超出者共 {sum(1 for f in fields if f['field'] in HARD_LIMITS and not f['ok'] and f['field'] in numeric)} 項。")

    # 4. 跨欄位與常態範圍
    soft_hits = []
    for name, v in numeric.items():
        lo, hi = SOFT_LIMITS[name]
        if name in normalized and not lo <= v <= hi:
            soft_hits.append(name)
            warnings.append(f"{LABELS[name]} {v:g} {UNITS[name]} 超出常態運轉範圍 [{lo:g}, {hi:g}]（示範值，請依銘牌調整），請確認量測是否正確")
    cross_warns = 0
    if ("current_a" in normalized and "pressure_mpa" in normalized
            and normalized["current_a"] < 1.0 and normalized["pressure_mpa"] > 0.5):
        warnings.append("電流接近 0 但壓力偏高，設備似乎未運轉卻有壓力，請確認兩個數值是否在同一時間量測")
        cross_warns = 1
    log.add(f"常態範圍（警告用，不擋儲存）：電流 [{SOFT_LIMITS['current_a'][0]:g}, {SOFT_LIMITS['current_a'][1]:g}] A、"
            f"壓力 [{SOFT_LIMITS['pressure_mpa'][0]:g}, {SOFT_LIMITS['pressure_mpa'][1]:g}] MPa；"
            f"超出 {len(soft_hits)} 項；跨欄位檢查（電流≈0 卻有壓力）產生 {cross_warns} 則警告。")

    # 5. 彙整
    errors = [f for f in fields if not f["ok"]]
    is_valid = not errors
    message = "FIELD_VALIDATION_PASSED" if is_valid else "FIELD_VALIDATION_FAILED"
    guardrail = ("PASSED" if not warnings else "PASSED_WITH_WARNINGS") if is_valid else \
        f"BLOCKED_BY_GUARDRAIL ({len(errors)} invalid field{'s' if len(errors) > 1 else ''})"
    log.add(f"防呆檢核狀態：{guardrail}。共 {len(fields)} 項欄位檢查，通過 {len(fields) - len(errors)}、失敗 {len(errors)}；警告 {len(warnings)} 則。")

    answer = ("所有欄位通過驗證。" + ("但有 %d 則警告需要留意。" % len(warnings) if warnings else "")) if is_valid else \
        "有 %d 個欄位未通過驗證：" % len(errors) + "；".join(f"{f['label']}（{f['message']}）" for f in errors)
    result = {
        "status": "success", "found": is_valid, "is_valid": is_valid, "message": message,
        "input_echo": {"current_a": clean_num(current_a), "pressure_mpa": clean_num(pressure_mpa)},
        "field_results": fields, "error_count": len(errors),
        "normalized_entry": normalized if is_valid else None,
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
        "limits": {"hard": HARD_LIMITS, "soft": SOFT_LIMITS},
        "steps": log.steps,
    }
    save_json(result, out_path)
    return result


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_12_repair_log_entry_validation ===")
    print(json.dumps(validate_repair_log_entry(45.2, 2.1), ensure_ascii=False, indent=2))
