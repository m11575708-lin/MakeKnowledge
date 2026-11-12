"""
_repair_log_store.py - page09 維修履歷儲存（JSON Lines）

檔案：data/repair_log_entries.jsonl，每行一筆案例。
以 (設備 ID, 維修時間, 故障碼, 處置說明) 的 SHA-1 雜湊防止重複儲存（例如連點兩次按鈕）。
目前儲存的紀錄不會自動併入 page08 的案例庫（data/repair_cases.json），避免未經審核的資料污染檢索結果。
"""

import hashlib
import json
import os
from datetime import datetime

try:
    from ._common import default_output_path
except ImportError:
    from _common import default_output_path


def _path() -> str:
    return default_output_path("repair_log_entries.jsonl")


def _read_all() -> list:
    path = _path()
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue   # 略過損毀的行
    return rows


def entry_hash(entry: dict) -> str:
    key = "|".join(str(entry.get(k, "")) for k in ("equipment_id", "repair_datetime", "error_code", "description"))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def is_duplicate(entry: dict) -> bool:
    h = entry_hash(entry)
    return any(r.get("hash") == h for r in _read_all())


def save_repair_entry(entry: dict, verdict: dict = None) -> dict:
    """entry 需為 skill_12 的 normalized_entry。回傳 {"saved","duplicate","entry_id",...}。"""
    required = ("equipment_id", "repair_datetime", "error_code", "description", "current_a", "pressure_mpa")
    missing = [k for k in required if k not in entry]
    if missing:
        return {"saved": False, "duplicate": False, "entry_id": None,
                "message": "缺少欄位：" + "、".join(missing)}
    h = entry_hash(entry)
    rows = _read_all()
    dup = next((r for r in rows if r.get("hash") == h), None)
    if dup:
        return {"saved": False, "duplicate": True, "entry_id": dup.get("entry_id"),
                "message": f"相同的維修紀錄已儲存過（{dup.get('entry_id')}），不重複儲存。"}
    now = datetime.now()
    entry_id = f"RL-{now:%Y%m%d}-{len(rows) + 1:04d}"
    record = {"entry_id": entry_id, "hash": h, "saved_at": now.strftime("%Y-%m-%d %H:%M:%S"),
              **{k: entry[k] for k in required}, "verdict": verdict or {}}
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"saved": True, "duplicate": False, "entry_id": entry_id, "message": f"已儲存為 {entry_id}。"}


def recent_entries(limit: int = 8) -> list:
    rows = _read_all()
    rows.sort(key=lambda r: (r.get("repair_datetime", ""), r.get("saved_at", "")), reverse=True)
    return rows[:max(1, min(int(limit), 50))]
