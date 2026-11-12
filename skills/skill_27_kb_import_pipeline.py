"""
skill_27_kb_import_pipeline.py - 知識庫匯入整理管線技能

對應系統規格：US-18 / 03. 工廠圖資與維修履歷匯入整理頁（呼叫順序：skill_27 → （感測器 CSV）skill_03 → 重跑模型類 Skill）
機制（非課堂演算法）：讀取與格式檢查 -> 正則清洗 -> SHA-256 雜湊去重 -> 筆數核對 -> 滑動視窗切片並寫入 SQLite 文件索引

說明（請務必讀）：
  * 檔案來源：只讀 data/uploads/ 底下「已上傳」的檔案，檔名只接受單純檔名（不含路徑）並確認解析後仍在該資料夾內。
  * 清洗：移除控制字元與零寬字元（re）、合併多餘空白、把 2026/10/3 14:05 之類的日期時間標準化為 ISO 格式
    （無法解析的日期保持原樣並警告，不會亂猜）。CSV 欄數不符的列視為格式錯誤列而丟棄並計數；超過 20% 整個檔案判失敗。
  * 去重：段落／資料列正規化（NFKC＋空白合併）後取 SHA-256；同檔內重複、以及和「先前匯入過的內容」重複者都被移除。
    整檔位元組完全相同（檔案 SHA-256 已存在）會被判定為「已匯入過」。雜湊相同才視為重複——內容相近但不同的段落不會被合併。
  * 筆數核對：讀進筆數 = 保留 + 檔內重複 + 索引內重複 + 空白列 + 格式錯誤列，且保留筆數 = 實際切片的筆數；不符則該檔「不寫入」。
  * 切片：固定長度滑動視窗（預設 500 字、重疊 50 字），可由 chunk 還原原文；寫入在單一交易內，寫入後再核對筆數，不符就 rollback。
  * 一個檔案失敗不影響其他檔案；失敗原因寫入匯入紀錄（import_files 資料表）。
  * dry_run=True 時完整執行所有檢查但「不寫入索引、不寫匯入紀錄、不產生暫存檔」，適合預覽或由 MCP 工具呼叫。
  * 匯入的文件一律標為內部資料（is_public=0），不會出現在民眾可見的文件清單。
"""

import hashlib
import json
import math
import os
import re
import secrets
import sys
import unicodedata
from datetime import datetime

try:
    from ._common import StepLog, default_output_path, project_root, save_json
    from . import _doc_readers as rd
    from . import _kb_store as kb
    from ._import_registry import detect_dataset
except ImportError:
    from _common import StepLog, default_output_path, project_root, save_json
    import _doc_readers as rd
    import _kb_store as kb
    from _import_registry import detect_dataset

SKILL_NAME = "skill_27_kb_import_pipeline"
FILE_TYPES = ["維修履歷", "感測器圖資", "設備規格書", "製程數據"]
MAX_FILES = 10
INVALID_ROW_LIMIT = 0.20
DUP_WARN = 0.50
MAX_CHUNKS = 20000
DEFAULT_RULES = {"strip_noise": True, "normalize_datetime": True, "dedupe": True, "chunk_size": 500, "overlap": 50}
NAME_RE = re.compile(r"^[\w.\-一-鿿]{1,120}$")
ILLEGAL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f�​-‏  ﻿]")
DT_RE = re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
WS_RE = re.compile(r"[ \t　]+")

PLAN = [
    ("讀取檔案與格式檢查", "File Read & Format Validation", "csv, zlib, re"),
    ("正則清洗（非法字元、日期時間標準化）", "Regular-expression Cleaning", "re, unicodedata"),
    ("SHA-256 雜湊去重", "SHA-256 Hash Deduplication", "hashlib"),
    ("筆數核對", "Row Count Reconciliation", "Python Built-in"),
    ("滑動視窗切片並寫入文件索引", "Sliding-window Chunking + SQLite Index Write", "sqlite3"),
]


def uploads_dir() -> str:
    return os.path.join(project_root(), "data", "uploads")


def staging_dir() -> str:
    return os.path.join(project_root(), "data", "staging")


def _norm_key(parts) -> str:
    s = "\x1f".join(WS_RE.sub(" ", unicodedata.normalize("NFKC", p)).strip() for p in parts)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def clean_text(s: str, strip_noise: bool) -> str:
    if strip_noise:
        s = ILLEGAL_RE.sub("", s).replace("\r\n", "\n").replace("\r", "\n")
        s = "\n".join(WS_RE.sub(" ", ln).strip() for ln in s.split("\n"))
        s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def norm_datetime(cell: str):
    """回傳 (新字串, 日期 YYYY-MM-DD 或 None, 是否格式像日期但無法解析)。"""
    m = DT_RE.match(cell)
    if not m:
        return cell, None, False
    y, mo, d, hh, mi, ss = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0))
    except ValueError:
        return cell, None, True
    date = dt.strftime("%Y-%m-%d")
    return (dt.strftime("%Y-%m-%d %H:%M:%S") if hh is not None else date), date, False


def sliding_windows(text: str, size: int, overlap: int):
    """固定長度滑動視窗；可還原：chunks[0] + Σ chunks[i][overlap:] == text。"""
    out, i, step = [], 0, size - overlap
    while True:
        out.append(text[i:i + size])
        if i + size >= len(text):
            break
        i += step
    return out


def _safe_path(name: str):
    """只接受單純檔名；解析後必須仍在 uploads 資料夾內。回傳 (path, error)。"""
    if not isinstance(name, str) or not NAME_RE.match(name) or ".." in name:
        return None, "檔名不合法（只接受單純檔名，不可含路徑或特殊字元）"
    base = os.path.realpath(uploads_dir())
    p = os.path.realpath(os.path.join(base, name))
    if os.path.dirname(p) != base:
        return None, "檔名不合法（超出上傳資料夾）"
    if not os.path.isfile(p):
        return None, "找不到已上傳的檔案（請先上傳）"
    return p, None


def import_kb_files(files=None, rules=None, file_type=None, dry_run: bool = False, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("kb_import_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    import_id = "IMP-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)
    started = datetime.now().isoformat(timespec="seconds")

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        result["import_id"] = import_id
        result["dry_run"] = dry_run
        save_json({k: v for k, v in result.items() if k != "files_detail_rows"}, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "import_progress_pct": 0, "rows_read": 0, "rows_cleaned_count": 0,
                       "duplicate_rate_pct": 0.0, "chunks_created_count": 0, "files": [], "failures": [],
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # ---------- 輸入驗證 ----------
    errors = []
    r = dict(DEFAULT_RULES)
    if rules is not None:
        if not isinstance(rules, dict):
            errors.append("rules 必須是物件")
        else:
            unknown = set(rules) - set(DEFAULT_RULES)
            if unknown:
                errors.append(f"未知的規則：{'、'.join(sorted(map(str, unknown)))}")
            r.update({k: v for k, v in rules.items() if k in DEFAULT_RULES})
    for k in ("strip_noise", "normalize_datetime", "dedupe"):
        if not isinstance(r[k], bool):
            errors.append(f"{k} 必須是 true 或 false")
    for k, lo, hi in (("chunk_size", 100, 5000), ("overlap", 0, 2500)):
        if isinstance(r[k], bool) or not isinstance(r[k], int) or not lo <= r[k] <= hi:
            errors.append(f"{k} 需為 {lo}–{hi} 的整數")
    if not errors and r["overlap"] >= r["chunk_size"]:
        errors.append("overlap 必須小於 chunk_size（否則視窗無法前進）")
    entries = []
    if not isinstance(files, (list, tuple)) or not files:
        errors.append("files 必須是非空的檔案清單")
    elif len(files) > MAX_FILES:
        errors.append(f"一次最多匯入 {MAX_FILES} 個檔案")
    else:
        for f in files:
            if isinstance(f, str):
                f = {"name": f}
            if not isinstance(f, dict) or "name" not in f:
                errors.append("files 的每一項必須是檔名字串或含 name 的物件")
                continue
            ft = f.get("file_type", file_type)
            if ft not in FILE_TYPES:
                errors.append(f"{f.get('name')}：file_type 必須是 {'、'.join(FILE_TYPES)} 之一")
                continue
            entries.append({"name": f["name"], "original": str(f.get("original_name") or f["name"])[:200], "file_type": ft})
        if len({e["name"] for e in entries}) != len(entries):
            errors.append("files 內有重複的檔名")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)

    conn = None
    if not dry_run:
        conn = kb.connect()
    elif os.path.exists(kb.db_path()):
        conn = kb.connect()          # 只讀用途（dry_run 不寫入）
    fl = []   # 每檔狀態
    for e in entries:
        fl.append({"file_name": e["original"], "stored_name": e["name"], "file_type": e["file_type"], "status": "pending",
                   "stages": {"read": "pending", "clean": "pending", "dedupe": "pending", "reconcile": "pending", "chunk": "pending"},
                   "rows_read": 0, "rows_cleaned": 0, "dropped_empty": 0, "dropped_invalid": 0, "dup_in_file": 0, "dup_in_index": 0,
                   "duplicates": 0, "duplicate_rate_pct": 0.0, "chunks": 0, "char_count": 0, "data_latest": None, "dataset": None,
                   "doc_id": None, "sha256": None, "staged_csv": None, "failure_stage": None, "failure_reason": None,
                   "_units": None, "_headers": None, "_data": None, "_ext": None, "_publish": None, "_hashes": None})

    def fail(f, stage, reason):
        f["status"], f["failure_stage"], f["failure_reason"] = "failed", stage, reason
        f["stages"][stage] = "failed"
        for k, v in f["stages"].items():
            if v == "pending":
                f["stages"][k] = "skipped"

    live = lambda: [f for f in fl if f["status"] == "pending"]   # noqa: E731

    # ---------- 1. 讀取 ----------
    for f in fl:
        path, err = _safe_path(f["stored_name"])
        if err:
            fail(f, "read", err)
            continue
        ext = os.path.splitext(f["stored_name"])[1].lower()
        if ext not in rd.ALLOWED_EXT:
            fail(f, "read", f"不支援的副檔名 {ext or '(無)'}（只支援 {', '.join(rd.ALLOWED_EXT)}）")
            continue
        size = os.path.getsize(path)
        if size == 0 or size > rd.MAX_BYTES:
            fail(f, "read", "檔案是空的" if size == 0 else f"檔案 {size / 1048576:.1f}MB 超過上限 {rd.MAX_BYTES // 1048576}MB")
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        f["sha256"] = hashlib.sha256(data).hexdigest()
        f["_ext"] = ext
        try:
            if ext == ".csv":
                f["_headers"], f["_units"] = rd.read_csv(data)
                f["dataset"] = detect_dataset(f["_headers"])
            elif ext == ".md":
                f["_units"] = rd.read_markdown(data)
            else:
                f["_units"] = rd.pdf_paragraphs(data)
        except rd.ReadError as ex:
            fail(f, "read", str(ex))
            continue
        f["rows_read"] = len(f["_units"])
        if f["rows_read"] == 0:
            fail(f, "read", "檔案沒有任何可用內容（沒有資料列或段落）")
            continue
        f["stages"]["read"] = "ok"
    ok_read = [f for f in fl if f["stages"]["read"] == "ok"]
    log.add(f"收到 {len(fl)} 個檔案，{len(ok_read)} 個讀取成功：" + "；".join(
        f"{f['file_name']}（{f['_ext'][1:].upper()}，{'資料列' if f['_ext'] == '.csv' else '段落'} {f['rows_read']} 筆）" for f in ok_read[:6])
        + ("；".join([""] + [f"{f['file_name']} 失敗：{f['failure_reason']}" for f in fl if f["status"] == "failed"][:4]) if len(ok_read) < len(fl) else "")
        + "。")

    # ---------- 2. 清洗 ----------
    date_unparsed = 0
    for f in live():
        units, kept, latest = f["_units"], [], []
        if f["_ext"] == ".csv":
            nh = len(f["_headers"])
            for row in units:
                if len(row) != nh:
                    f["dropped_invalid"] += 1
                    continue
                cells = []
                for h, c in zip(f["_headers"], row):
                    c = clean_text(c, r["strip_noise"]).replace("\n", " ")
                    if r["normalize_datetime"]:
                        c, d, bad = norm_datetime(c)
                        date_unparsed += 1 if bad else 0
                        if d:
                            latest.append(d)
                    mm = MONTH_RE.match(c)
                    if mm and 1 <= int(mm.group(2)) <= 12 and h.lower() in ("month", "date", "time", "月份", "日期"):
                        latest.append(f"{mm.group(1)}-{mm.group(2)}-01")
                    cells.append(c)
                if not any(cells):
                    f["dropped_empty"] += 1
                    continue
                kept.append(cells)
            if f["rows_read"] and f["dropped_invalid"] / f["rows_read"] > INVALID_ROW_LIMIT:
                fail(f, "clean", f"{f['dropped_invalid']}/{f['rows_read']} 列（{f['dropped_invalid'] / f['rows_read'] * 100:.0f}%）欄數與標頭不符，格式錯誤，整份拒絕")
                continue
        else:
            for p in units:
                c = clean_text(p, r["strip_noise"])
                if not c:
                    f["dropped_empty"] += 1
                    continue
                kept.append(c)
        if not kept:
            fail(f, "clean", "清洗後沒有任何有效內容")
            continue
        f["_units"] = kept
        f["data_latest"] = max(latest) if latest else None
        f["stages"]["clean"] = "ok"
    tot_read = sum(f["rows_read"] for f in fl)
    log.add(("已套用：" + "、".join(n for n, k in (("移除非法字元與合併空白", "strip_noise"), ("日期時間標準化", "normalize_datetime")) if r[k]) if (r["strip_noise"] or r["normalize_datetime"]) else "未啟用任何清洗規則")
            + f"。{len(live())} 個檔案通過清洗；丟棄空白列／段落 {sum(f['dropped_empty'] for f in fl)} 筆、格式錯誤列 {sum(f['dropped_invalid'] for f in fl)} 筆"
            + (f"；{date_unparsed} 個儲存格長得像日期但無法解析（已保持原樣）" if date_unparsed else "") + "。"
            + "".join(f"【{f['file_name']} 失敗：{f['failure_reason']}】" for f in fl if f["failure_stage"] == "clean"))

    # ---------- 3. 去重 ----------
    for f in live():
        units = f["_units"]
        keys = [_norm_key(u if f["_ext"] == ".csv" else [u]) for u in units]
        f["_publish"] = None
        if f["_ext"] == ".csv":
            seen_p, pub = set(), []
            for u, k in zip(units, keys):
                if r["dedupe"] and k in seen_p:
                    continue
                seen_p.add(k)
                pub.append(u)
            f["_publish"] = pub                              # 發佈用：整份清洗後內容（僅去掉檔內重複）
        file_dup = conn is not None and kb.doc_by_sha(conn, f["sha256"]) is not None
        if file_dup:                                          # 整檔已匯入過：與去重開關無關，一律不重複寫入
            f["dup_in_index"] = len(units)
            units, keys = [], []
        elif r["dedupe"]:
            seen, new_u, new_k = set(), [], []
            for u, k in zip(units, keys):
                if k in seen:
                    f["dup_in_file"] += 1
                else:
                    seen.add(k)
                    new_u.append(u)
                    new_k.append(k)
            if conn is not None:
                known = kb.existing_hashes(conn, new_k)
                pairs = [(u, k) for u, k in zip(new_u, new_k) if k not in known]
                f["dup_in_index"] = len(new_u) - len(pairs)
                new_u, new_k = [x[0] for x in pairs], [x[1] for x in pairs]
            units, keys = new_u, new_k
        f["_units"], f["_hashes"] = units, keys
        f["duplicates"] = f["dup_in_file"] + f["dup_in_index"]
        f["rows_cleaned"] = len(units)
        f["duplicate_rate_pct"] = round(f["duplicates"] / f["rows_read"] * 100, 1) if f["rows_read"] else 0.0
        f["_file_dup"] = file_dup
        f["stages"]["dedupe"] = "ok"
    dups = sum(f["duplicates"] for f in fl)
    log.add(("以 SHA-256（NFKC 正規化＋空白合併後）比對：" if r["dedupe"] else "去重規則未啟用，保留所有重複內容。") +
            (f"檔內重複 {sum(f['dup_in_file'] for f in fl)} 筆、與索引內既有內容重複 {sum(f['dup_in_index'] for f in fl)} 筆，"
             f"整體重複率 {dups / tot_read * 100:.1f}%。" if r["dedupe"] and tot_read else "")
            + "".join(f"【{f['file_name']} 整檔位元組與已匯入的文件相同，視為已匯入過】" for f in fl if f.get("_file_dup")))

    # ---------- 4. 筆數核對 ----------
    for f in live():
        expect = f["rows_cleaned"] + f["dup_in_file"] + f["dup_in_index"] + f["dropped_empty"] + f["dropped_invalid"]
        if expect != f["rows_read"] or f["rows_cleaned"] != len(f["_units"]):
            fail(f, "reconcile", f"筆數核對不符：讀進 {f['rows_read']} ≠ 保留 {f['rows_cleaned']} + 重複 {f['duplicates']} + 空白 {f['dropped_empty']} + 錯誤 {f['dropped_invalid']}，未寫入")
            continue
        f["stages"]["reconcile"] = "ok"
    log.add("核對式：讀進筆數 = 保留 + 檔內重複 + 索引內重複 + 空白 + 格式錯誤；" +
            "；".join(f"{f['file_name']}：{f['rows_read']} = {f['rows_cleaned']} + {f['dup_in_file']} + {f['dup_in_index']} + {f['dropped_empty']} + {f['dropped_invalid']}"
                      f"（{'通過' if f['stages']['reconcile'] == 'ok' else '不符'}）" for f in fl if f["stages"]["reconcile"] != "skipped" and f["failure_stage"] in (None, "reconcile"))[:600] + "。"
            + "".join(f"【{f['file_name']} {f['failure_reason']}】" for f in fl if f["failure_stage"] == "reconcile"))

    # ---------- 5. 切片並寫入 ----------
    now = datetime.now().isoformat(timespec="seconds")
    if conn is not None and not dry_run:
        kb.start_import(conn, import_id, started, len(fl))
    total_chunks = 0
    for f in live():
        if f["rows_cleaned"] == 0:
            f["status"] = "duplicate_file" if f.get("_file_dup") else "no_new_content"
            f["stages"]["chunk"] = "skipped"
            if f["_ext"] == ".csv" and f["_publish"] and not f.get("_file_dup") and not dry_run:
                f["staged_csv"] = _stage_csv(f)            # 內容都已在索引內，但整份資料仍可發佈為分析資料集
            continue
        text = "\n".join(" | ".join(f"{h}={v}" for h, v in zip(f["_headers"], u)) for u in f["_units"]) if f["_ext"] == ".csv" \
            else "\n\n".join(f["_units"])
        chunks = sliding_windows(text, r["chunk_size"], r["overlap"])
        if len(chunks) > MAX_CHUNKS:
            fail(f, "chunk", f"切出 {len(chunks)} 個切片，超過上限 {MAX_CHUNKS}，請調大 chunk_size 或拆檔")
            continue
        f["chunks"], f["char_count"] = len(chunks), len(text)
        f["doc_id"] = "DOC-" + f["sha256"][:12].upper()
        if not dry_run:
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO documents (doc_id, source_name, file_type, category, file_sha256, stored_name, ext, is_public, license_type, "
                        "source_url, updated_at, data_latest, content_preview, char_count, row_count, chunk_count, imported_at, import_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (f["doc_id"], f["file_name"], f["file_type"], f["file_type"], f["sha256"], f["stored_name"], f["_ext"][1:], 0,
                         "內部資料（非公開）", f"internal://{f['doc_id']}", now[:10], f["data_latest"], text[:200], len(text),
                         f["rows_cleaned"], len(chunks), now, import_id))
                    conn.executemany("INSERT INTO chunks (doc_id, seq, text, text_sha256) VALUES (?,?,?,?)",
                                     [(f["doc_id"], i, c, hashlib.sha256(c.encode("utf-8")).hexdigest()) for i, c in enumerate(chunks)])
                    conn.executemany("INSERT OR IGNORE INTO row_hashes (hash, doc_id) VALUES (?,?)", [(h, f["doc_id"]) for h in f["_hashes"]])
                    n_db = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (f["doc_id"],)).fetchone()[0]
                    if n_db != len(chunks):
                        raise RuntimeError(f"寫入後核對不符：應有 {len(chunks)} 個切片，資料庫只有 {n_db}")
            except Exception as ex:     # noqa: BLE001
                f["chunks"] = 0
                fail(f, "chunk", f"寫入索引失敗（已 rollback）：{ex}")
                continue
            if f["_ext"] == ".csv" and f["_publish"]:
                f["staged_csv"] = _stage_csv(f)
        f["status"] = "imported"
        f["stages"]["chunk"] = "ok"
        total_chunks += len(chunks)

    # 匯入紀錄
    if not dry_run and conn is not None:
        for f in fl:
            kb.log_file(conn, import_id, {
                "file_name": f["file_name"], "file_type": f["file_type"], "status": f["status"], "rows_read": f["rows_read"],
                "rows_cleaned": f["rows_cleaned"], "duplicates": f["duplicates"], "duplicate_rate_pct": f["duplicate_rate_pct"],
                "chunks": f["chunks"], "failure_stage": f["failure_stage"], "failure_reason": f["failure_reason"], "stages": f["stages"]}, now)
        failed_n = sum(1 for f in fl if f["status"] == "failed")
        kb.finish_import(conn, import_id, datetime.now().isoformat(timespec="seconds"),
                         "failed" if failed_n == len(fl) else ("partial" if failed_n else "success"))
    if conn is not None:
        conn.close()

    # ---------- 彙整 ----------
    done = [f for f in fl if f["status"] in ("imported", "duplicate_file", "no_new_content")]
    failures = [{"file": f["file_name"], "stage": f["failure_stage"], "reason": f["failure_reason"]} for f in fl if f["status"] == "failed"]
    tot_cleaned = sum(f["rows_cleaned"] for f in fl)
    rate = round(sum(f["duplicates"] for f in fl) / tot_read * 100, 1) if tot_read else 0.0
    warnings = []
    if date_unparsed:
        warnings.append(f"{date_unparsed} 個儲存格長得像日期但無法解析（例如月份或日期超出範圍），已保持原樣，請檢查來源")
    for f in fl:
        if f["rows_read"] and f["status"] != "failed" and f["dropped_invalid"] / f["rows_read"] > 0.05:
            warnings.append(f"{f['file_name']}：{f['dropped_invalid']} 列欄數不符被丟棄（{f['dropped_invalid'] / f['rows_read'] * 100:.0f}%）")
        if f["status"] == "duplicate_file":
            warnings.append(f"{f['file_name']} 與已匯入的文件位元組完全相同，未重複寫入")
        elif f["status"] == "no_new_content":
            warnings.append(f"{f['file_name']} 的所有內容都已存在於索引，沒有新增切片")
    if r["dedupe"] and rate > DUP_WARN * 100:
        warnings.append(f"整體重複率 {rate}%（> {DUP_WARN * 100:.0f}%），請確認是否重複上傳")
    if any(f["_ext"] == ".pdf" for f in fl if f["_ext"]):
        warnings.append("PDF 為基本版抽字（僅限文字型 PDF），抽出的段落以 PDF 內的文字區塊為單位，排版與表格結構不會保留")
    if dry_run:
        warnings.append("這是預覽（dry_run）：沒有寫入索引或匯入紀錄")
    for f in fl:
        for k in ("_units", "_headers", "_data", "_publish", "_hashes"):
            f.pop(k, None)
        f.pop("_file_dup", None)
        f.pop("_ext", None)
    pct = round(len(done) / len(fl) * 100) if fl else 0
    if not done:
        guardrail = "BLOCKED_BY_GUARDRAIL (all files failed)"
    else:
        guardrail = "PASSED_WITH_WARNINGS" if (warnings or failures) else "PASSED"
    log.add(f"{'預覽' if dry_run else '寫入'}結果：{len(done)}/{len(fl)} 個檔案完成，保留 {tot_cleaned} 筆、切片 {total_chunks} 個"
            f"{'（未寫入）' if dry_run else '，已寫入 SQLite 文件索引與匯入紀錄'}。防呆檢核狀態：{guardrail}。"
            + ("".join(f"【{x['file']}：{x['stage']} 階段失敗】" for x in failures[:4])))
    msg = (f"{len(done)}/{len(fl)} 個檔案匯入完成，保留 {tot_cleaned} 筆、重複率 {rate}%、產生 {total_chunks} 個切片。" if done
           else "所有檔案都匯入失敗：" + "；".join(f"{x['file']}（{x['reason']}）" for x in failures[:3]))
    return finish({
        "status": "success", "found": bool(done), "import_progress_pct": pct, "rows_read": tot_read, "rows_cleaned_count": tot_cleaned,
        "duplicate_rate_pct": rate, "duplicates_removed": sum(f["duplicates"] for f in fl), "chunks_created_count": total_chunks,
        "files": fl, "failures": failures, "rules": r, "warnings": warnings, "guardrail_status": guardrail, "answer_text": msg,
    })


def _stage_csv(f):
    """把清洗後的整份 CSV（供發佈為分析資料集）寫到暫存資料夾，回傳相對路徑。"""
    import csv
    os.makedirs(staging_dir(), exist_ok=True)
    path = os.path.join(staging_dir(), f"{f['sha256'][:16]}.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(f["_headers"])
        w.writerows(f["_publish"])
    return os.path.relpath(path, project_root())


if __name__ == "__main__":
    print(json.dumps(import_kb_files(files=["demo.md"], file_type="設備規格書", dry_run=True), ensure_ascii=False, indent=2)[:1500])
