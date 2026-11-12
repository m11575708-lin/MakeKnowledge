"""
skill_28_data_freshness_check.py - 資料新鮮度檢查技能

對應系統規格：US-19 / 04. 製造知識庫維運與回答品質評估頁
機制（非課堂演算法）：蒐集各資料集最新日期 -> 落後月數 -> 時間衰減權重 W(t) = e^(-λ·Δt) -> 門檻比對

說明（請務必讀）：
  * 「最新日期」有三種可信度，每個資料集都會標出 date_basis：
      data         資料內容裡真的有日期（匯入文件的 data_latest、CSV 的 date／month／timestamp 欄）——最可靠
      file_mtime   資料裡沒有日期欄，只能用檔案修改時間——代表「這個檔案多久沒更新」，不代表資料本身的時間
      import_time  匯入的文件內容找不到日期，只知道匯入時間
      none         沒有檔案（使用合成示範資料）或讀不到——無法判斷，不計入「需更新」
  * 落後月數 Δt：基準日的 (年×12+月) 減去最新日期的 (年×12+月)；最新日期含「日」時，基準日的日小於它則再減 1。
    例：最新 2026-06、基準日 2026-11-11 → 落後 5 個月，權重 e^(-0.1×5) = 0.6065（與規格範例一致）。
  * 超過門檻（lag_months > max_lag_months，預設 3）才提醒；剛好等於門檻不提醒。
  * 最新日期晚於基準日（未來日期）視為資料異常：落後記為 0 並加警語，不當作「很新」。
  * freshness_index = 有日期的資料集權重平均（statistics.mean），僅供參考，不取代逐項檢視。
  * 本技能只檢查「資料有多舊」，無法判斷「內容是否仍符合現行法規」。法規是否修訂需要人工對照官方公告。
  * 只讀取：不修改任何資料；SQLite 以唯讀模式開啟。結果存成 data/data_freshness_result.json。
"""

import csv
import math
import os
import re
import sqlite3
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from ._common import StepLog, default_output_path, project_root, save_json
    from ._import_registry import DATASETS
    from . import _kb_store as kb
except ImportError:
    from _common import StepLog, default_output_path, project_root, save_json
    from _import_registry import DATASETS
    import _kb_store as kb

SKILL_NAME = "skill_28_data_freshness_check"
DEFAULT_LAG = 3
DEFAULT_LAMBDA = 0.1
MAX_LAG_LIMIT = 120
MAX_LAMBDA = 2.0
MAX_CSV_ROWS = 200000
DATE_COLS = ("date", "datetime", "timestamp", "time", "month", "日期", "時間", "月份")
DATE_RE = re.compile(r"^\s*(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?(?:[ T].*)?$")
KB_TYPES = ["維修履歷", "感測器圖資", "設備規格書", "製程數據"]

PLAN = [
    ("驗證基準日與參數", "Input Validation Guardrail", "datetime, re"),
    ("蒐集各資料集最新日期", "Dataset Latest-date Scan", "sqlite3, csv, os"),
    ("計算落後月數 Δt", "Calendar-month Lag", "datetime"),
    ("計算時間衰減權重 W(t)", "Exponential Time Decay W(t)=e^(-λΔt)", "math, statistics"),
    ("門檻比對與新鮮度判定", "Threshold-based Freshness Guardrail", "Python Control Flow"),
]


def parse_latest(text):
    """'2026-06' / '2026-06-15' / '2026/6/5 14:30' -> (date, precision) 或 None。月份精度的日記為 1。"""
    if not isinstance(text, str):
        return None
    m = DATE_RE.match(text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        return date(y, mo, int(d) if d else 1), ("day" if d else "month")
    except ValueError:
        return None


def lag_months_between(latest: date, precision: str, today: date) -> int:
    """日曆月差；精度為「日」且基準日的日還沒到時再減 1。可能為負（未來日期），由呼叫端處理。"""
    diff = (today.year * 12 + today.month) - (latest.year * 12 + latest.month)
    if precision == "day" and today.day < latest.day:
        diff -= 1
    return diff


def _fmt(d: date, precision: str) -> str:
    return d.strftime("%Y-%m") if precision == "month" else d.strftime("%Y-%m-%d")


def _max_parsed(values):
    best, bad, n = None, 0, 0
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        n += 1
        p = parse_latest(str(v))
        if p is None:
            bad += 1
            continue
        if best is None or p[0] > best[0] or (p[0] == best[0] and p[1] == "day"):
            best = p
    return best, bad, n


def _csv_latest(path):
    """回傳 (latest(date, precision) | None, 日期欄名稱 | None, 有效列數, 無效日期數, 總列數)。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        col = next((c for c in cols if c.strip().lower() in DATE_COLS or c.strip() in DATE_COLS), None)
        vals, total = [], 0
        for rec in reader:
            total += 1
            if total > MAX_CSV_ROWS:
                break
            if col:
                vals.append(rec.get(col))
    if not col:
        return None, None, 0, 0, total
    best, bad, n = _max_parsed(vals)
    return best, col, n - bad, bad, total


def _ro_connect():
    p = kb.db_path()
    if not os.path.isfile(p):
        return None
    return sqlite3.connect(Path(p).as_uri() + "?mode=ro", uri=True, timeout=5)


def _scan_documents(notes):
    """匯入文件（SQLite）依檔案類型彙整。回傳 dataset 字典清單。"""
    out = []
    try:
        conn = _ro_connect()
        if conn is None:
            return out
        try:
            rows = conn.execute(
                "SELECT file_type, COUNT(*), MAX(data_latest), MAX(imported_at) FROM documents GROUP BY file_type").fetchall()
            for ftype, n, dl, imp in rows:
                last = conn.execute(
                    "SELECT status, created_at, file_name, failure_reason FROM import_files WHERE file_type = ? ORDER BY id DESC LIMIT 1",
                    (ftype,)).fetchone()
                p = parse_latest(dl) if dl else None
                if p:
                    latest, prec, basis = p[0], p[1], "data"
                else:
                    pi = parse_latest(imp[:10]) if imp else None
                    latest, prec, basis = (pi[0], "day", "import_time") if pi else (None, None, "none")
                out.append({"name": f"匯入文件・{ftype}", "kind": "documents", "latest_date": latest, "precision": prec, "date_basis": basis,
                            "n_records": n, "source": "data/kb_index.sqlite",
                            "note": None if basis == "data" else "文件內容找不到日期，只知道匯入時間；無法代表資料本身的新舊",
                            "last_event": ({"type": "import", "status": last[0], "at": last[1], "file": last[2], "reason": last[3]} if last else None)})
        finally:
            conn.close()
    except sqlite3.Error as e:
        notes.append(f"讀取文件索引失敗：{e}")
    return out


def _last_publishes():
    res = {}
    try:
        conn = _ro_connect()
        if conn is None:
            return res
        try:
            for ds, ok, n, at, err, fn in conn.execute(
                    "SELECT dataset, ok, n_rows, published_at, error, file_name FROM dataset_publishes ORDER BY id"):
                res[ds] = {"type": "publish", "status": "ok" if ok else "failed", "at": at, "rows": n, "reason": err, "file": fn}
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return res


def _scan_csv_datasets(notes):
    out, pubs = [], _last_publishes()
    ddir = os.path.join(project_root(), "data")
    for key, d in DATASETS.items():
        path = os.path.join(ddir, d["filename"])
        base = {"name": f"分析資料・{d['label']}", "kind": "analysis_csv", "dataset_key": key, "source": f"data/{d['filename']}",
                "last_event": pubs.get(key), "latest_date": None, "precision": None, "date_basis": "none", "n_records": 0, "note": None}
        if not os.path.isfile(path):
            base["note"] = f"未放入 data/{d['filename']}，目前使用合成示範資料，無法判斷新舊"
            out.append(base)
            continue
        try:
            latest, col, n_ok, n_bad, total = _csv_latest(path)
        except (OSError, csv.Error, UnicodeDecodeError) as e:
            base["note"] = f"讀取失敗：{e}"
            out.append(base)
            continue
        base["n_records"] = total
        if latest:
            base.update(latest_date=latest[0], precision=latest[1], date_basis="data")
            base["note"] = f"取自「{col}」欄" + (f"（另有 {n_bad} 筆日期無法解析）" if n_bad else "")
        else:
            mt = datetime.fromtimestamp(os.path.getmtime(path)).date()
            base.update(latest_date=mt, precision="day", date_basis="file_mtime")
            base["note"] = ("日期欄無法解析，改用檔案修改時間" if col else "資料沒有日期欄，改用檔案修改時間（代表檔案多久沒更新，不是資料本身的時間）")
        out.append(base)
    return out


def _scan_docs_folder(notes):
    """skill_01 檢索用的 docs/ 資料夾（.txt/.md）。依 skill_01 的規則把檔名含 sop 的歸為 SOP／維修文件。"""
    ddir = os.path.join(project_root(), "docs")
    groups = {"regulations": [], "repairs": []}
    if os.path.isdir(ddir):
        for fn in os.listdir(ddir):
            fp = os.path.join(ddir, fn)
            if fn.lower().endswith((".txt", ".md")) and os.path.isfile(fp):
                groups["repairs" if "sop" in fn.lower() else "regulations"].append(os.path.getmtime(fp))
    labels = {"regulations": "檢索文件・法規與標準（docs/）", "repairs": "檢索文件・SOP 與維修（docs/）"}
    out = []
    for k, mts in groups.items():
        item = {"name": labels[k], "kind": "docs_folder", "source": "docs/", "last_event": None, "n_records": len(mts), "note": None}
        if mts:
            item.update(latest_date=datetime.fromtimestamp(max(mts)).date(), precision="day", date_basis="file_mtime",
                        note="依檔案修改時間；全新複製的專案會顯示複製當天，請以官方公告日期為準")
        else:
            item.update(latest_date=None, precision=None, date_basis="none", note="docs/ 內沒有這類文件")
        out.append(item)
    return out


def check_data_freshness(today=None, max_lag_months=DEFAULT_LAG, decay_lambda=DEFAULT_LAMBDA,
                         system_version=None, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("data_freshness_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    generated_at = datetime.now().isoformat(timespec="seconds")

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        result["generated_at"] = generated_at
        result["system_version"] = system_version
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "datasets": [], "data_freshness_status": "無法判斷",
                       "expiration_warning": [], "stale_count": 0, "unknown_count": 0, "freshness_index": None,
                       "params": {"today": None, "max_lag_months": None, "decay_lambda": None},
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # ---------- 1. 輸入驗證 ----------
    errors, warnings = [], []
    t = None
    if today is None or today == "":
        t = date.today()
    elif isinstance(today, str):
        p = parse_latest(today) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", today) else None
        if p is None:
            errors.append("基準日格式錯誤，需為 YYYY-MM-DD")
        else:
            t = p[0]
    else:
        errors.append("基準日必須是 YYYY-MM-DD 字串")
    if t is not None and not (date(2000, 1, 1) <= t <= date(2100, 12, 31)):
        errors.append("基準日需介於 2000-01-01 與 2100-12-31")
        t = None
    if isinstance(max_lag_months, bool) or not isinstance(max_lag_months, int) or not 0 <= max_lag_months <= MAX_LAG_LIMIT:
        errors.append(f"落後門檻 max_lag_months 必須是 0–{MAX_LAG_LIMIT} 的整數（月）")
    if isinstance(decay_lambda, bool) or not isinstance(decay_lambda, (int, float)) or not math.isfinite(decay_lambda) \
            or not 0 <= decay_lambda <= MAX_LAMBDA:
        errors.append(f"衰減係數 decay_lambda 必須是 0–{MAX_LAMBDA} 的有限數值")
    if errors:
        log.add("輸入驗證失敗：" + "；".join(errors))
        return blocked("輸入未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "輸入未通過驗證：" + "；".join(errors), errors)
    if t > date.today():
        warnings.append(f"基準日 {t} 晚於今天，結果是「假設到那天」的模擬，不是目前實況")
    log.add(f"基準日 {t}、落後門檻 {max_lag_months} 個月、衰減係數 λ={decay_lambda}，皆通過檢查。")

    # ---------- 2. 蒐集最新日期 ----------
    notes = []
    items = _scan_documents(notes) + _scan_csv_datasets(notes) + _scan_docs_folder(notes)
    warnings += notes
    by_basis = {}
    for it in items:
        by_basis[it["date_basis"]] = by_basis.get(it["date_basis"], 0) + 1
    log.add(f"掃描 {len(items)} 個資料集：資料內日期 {by_basis.get('data', 0)} 個、檔案修改時間 {by_basis.get('file_mtime', 0)} 個、"
            f"匯入時間 {by_basis.get('import_time', 0)} 個、無法判斷 {by_basis.get('none', 0)} 個。")

    # ---------- 3. 落後月數 ----------
    for it in items:
        d = it.pop("latest_date")
        prec = it.pop("precision")
        if d is None:
            it.update(latest=None, lag_months=None, future=False)
            continue
        raw = lag_months_between(d, prec, t)
        it["latest"] = _fmt(d, prec)
        it["future"] = raw < 0
        it["lag_months"] = max(raw, 0)
        if raw < 0:
            warnings.append(f"「{it['name']}」最新日期 {it['latest']} 晚於基準日，資料可能有誤，落後月數以 0 計")
    known = [it for it in items if it["lag_months"] is not None]
    log.add("落後月數 Δt = (基準日年×12+月) − (最新日期年×12+月)，日期含「日」且基準日還沒到該日時再減 1；"
            + ("；".join(f"{it['name']} 落後 {it['lag_months']} 個月" for it in known[:6]) if known else "沒有任何資料集有日期可算。")
            + ("（其餘略）" if len(known) > 6 else ""))

    # ---------- 4. 時間衰減權重 ----------
    for it in items:
        it["weight"] = round(math.exp(-decay_lambda * it["lag_months"]), 4) if it["lag_months"] is not None else None
    ws = [it["weight"] for it in known]
    fidx = round(statistics.mean(ws), 4) if ws else None
    log.add(f"權重 W(t) = e^(−λ·Δt)，λ={decay_lambda}（半衰期約 {math.log(2) / decay_lambda:.1f} 個月）；" if decay_lambda > 0
            else "λ=0：不做時間衰減，所有權重為 1；" + (f"有日期資料集的平均權重（新鮮度指數）為 {fidx}。" if fidx is not None else "沒有可平均的權重。"))
    if decay_lambda > 0:
        log.steps[-1]["description"] += (f"有日期資料集的平均權重（新鮮度指數）為 {fidx}。" if fidx is not None else "沒有可平均的權重。")

    # ---------- 5. 門檻比對 ----------
    for it in items:
        if it["lag_months"] is None:
            it["status"], it["warning"] = "unknown", False
        else:
            it["warning"] = it["lag_months"] > max_lag_months
            it["status"] = "stale" if it["warning"] else "fresh"
    stale = [it for it in items if it["status"] == "stale"]
    unknown = [it for it in items if it["status"] == "unknown"]
    weak = [it for it in known if it["date_basis"] in ("file_mtime", "import_time")]
    if not known:
        status_txt = "無法判斷"
        warnings.append("沒有任何資料集有可用的日期，無法判斷新鮮度。請先匯入資料或放入含日期欄的 CSV")
    elif stale:
        status_txt = "需更新"
    else:
        status_txt = "正常"
    if unknown and known:
        warnings.append(f"{len(unknown)} 個資料集無法判斷新舊（沒有檔案或沒有日期），未計入「需更新」")
    if weak:
        warnings.append(f"{len(weak)} 個資料集的日期是「檔案／匯入時間」而非資料本身的日期，可信度較低")
    expiration = [f"{it['name']}：最新 {it['latest']}，已落後 {it['lag_months']} 個月（門檻 {max_lag_months}），權重 {it['weight']}" for it in
                  sorted(stale, key=lambda x: -x["lag_months"])]
    guardrail = "PASSED" if (known and not warnings) else "PASSED_WITH_WARNINGS"
    log.add(f"落後超過 {max_lag_months} 個月者標為需更新：{len(stale)} 個資料集超過門檻、{len(unknown)} 個無法判斷。"
            f"整體判定：{status_txt}。防呆檢核狀態：{guardrail}。")

    answer = (f"基準日 {t}：{status_txt}。{len(stale)} 個資料集落後超過 {max_lag_months} 個月，{len(unknown)} 個無法判斷"
              + (f"，新鮮度指數 {fidx}。" if fidx is not None else "。"))
    return finish({
        "status": "success", "found": True, "datasets": items, "data_freshness_status": status_txt,
        "expiration_warning": expiration, "stale_count": len(stale), "unknown_count": len(unknown), "known_count": len(known),
        "freshness_index": fidx,
        "params": {"today": t.isoformat(), "max_lag_months": max_lag_months, "decay_lambda": decay_lambda},
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    import json
    r = check_data_freshness(today="2026-11-11")
    print(json.dumps({k: v for k, v in r.items() if k != "steps"}, ensure_ascii=False, indent=2)[:2500], file=sys.stdout)
