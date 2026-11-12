"""
skill_26_document_catalog_query.py - 文件目錄查詢技能

對應系統規格：US-17 / 02. 製造規範與技術文件收錄頁
機制（非課堂演算法）：驗證身分與條件 -> 載入文件元資料 -> 參數化 SQL 過濾（角色、類別、日期、關鍵字）-> 排序分頁 -> 可見性核對

說明（請務必讀）：
  * 文件來源：docs/ 資料夾的 .txt/.md（skill_01 檢索用的語料）＋ skill_27 匯入索引（data/kb_index.sqlite，唯讀開啟）。
    兩者合併後載入「記憶體內」的 sqlite3 表，再用參數化 SQL 過濾——查詢條件從不拼接進 SQL 字串。
  * 角色與可見性（規則在 _catalog.py）：role="public" 只看得到 is_public=1 的文件；內部角色看得到全部。
    docs/ 的文件預設「不公開」，必須在 data/catalog_manifest.json 明確寫 is_public: true 才會出現在民眾的清單。
    角色不認得時一律拒絕（fail closed），不會退回成公開或內部。
  * 結果輸出前再核對一次：role="public" 的結果只要出現 is_public≠1 的列就整個攔下，不輸出任何文件。
  * 關鍵字比對 source_name、doc_id、category、content_preview，以及 docs/ 文件正文的前 20000 字；
    匯入文件只比對預覽（前 200 字），因為完整內文在切片裡、此技能不全文掃描。
  * 沒有登記 category／updated_at／license 的 docs/ 文件：類別依檔名推測（category_inferred=true）、更新日取檔案修改日、
    授權標為「未標註」。這些是保守預設，不是文件本身的真實資訊，請在 manifest 補上。
  * 結果存成 data/document_catalog_result.json（只存條件與筆數摘要，不存文件內容）。
"""

import math
import os
import re
import sys
from datetime import datetime

try:
    from ._common import StepLog, default_output_path, save_json
    from . import _catalog as cat
    from . import _kb_store as kb
except ImportError:
    from _common import StepLog, default_output_path, save_json
    import _catalog as cat
    import _kb_store as kb

SKILL_NAME = "skill_26_document_catalog_query"
MAX_LIMIT = 200
MAX_KEYWORD = 100
CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

PLAN = [
    ("驗證身分與篩選條件", "Role & Input Validation Guardrail", "re, datetime"),
    ("載入文件元資料", "Metadata Loading (docs/ + import index)", "os, json, sqlite3"),
    ("參數化 SQL 過濾", "Parameterised SQL Filtering (role, category, date, keyword)", "sqlite3"),
    ("排序與分頁", "ORDER BY updated_at DESC + LIMIT/OFFSET", "sqlite3"),
    ("可見性核對與輸出組裝", "Visibility Re-check Guardrail", "Python Control Flow"),
]

PUBLIC_FIELDS = ("doc_id", "source_name", "category", "category_inferred", "updated_at", "license_type", "content_preview", "source_url",
                 "char_count", "chunk_count", "origin")


def _row_dict(cur_row, cols, internal):
    d = dict(zip(cols, cur_row))
    d["category_inferred"] = bool(d.get("category_inferred"))
    if internal:
        d["is_public"] = bool(d.get("is_public"))
    else:
        d.pop("is_public", None)
        d.pop("imported_at", None)
    d.pop("search_text", None)
    return d


def query_document_catalog(role="public", categories=None, start_date=None, end_date=None, keyword=None,
                           limit=50, offset=0, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("document_catalog_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    generated_at = datetime.now().isoformat(timespec="seconds")

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        result["generated_at"] = generated_at
        save_json({"generated_at": generated_at, "role": role if isinstance(role, str) else None, "found": result.get("found"),
                   "total": result.get("total"), "guardrail_status": result.get("guardrail_status"),
                   "filters": result.get("filters"), "steps": log.steps}, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "documents": [], "total": 0, "categories_available": [], "filters": None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # ---------- 1. 驗證 ----------
    errors = []
    view = cat.view_of_role(role) if isinstance(role, str) else None
    if view is None:
        log.add("角色不在允許清單內，拒絕查詢。")
        return blocked("角色不認得", "BLOCKED_BY_GUARDRAIL (unknown role)", "無法辨識的角色，已拒絕查詢（不會預設放行）。")
    cats = None
    if categories is not None:
        if not isinstance(categories, (list, tuple)) or len(categories) > 20 or not all(isinstance(c, str) and 0 < len(c) <= 40 for c in categories):
            errors.append("categories 必須是最多 20 個、每個 1–40 字的字串清單")
        else:
            cats = sorted(set(categories)) or None
    for name, v in (("start_date", start_date), ("end_date", end_date)):
        if v not in (None, "") and not cat.valid_date(v):
            errors.append(f"{name} 需為 YYYY-MM-DD")
    sd, ed = (start_date or None), (end_date or None)
    if not errors and sd and ed and sd > ed:
        errors.append("起始日期不可晚於結束日期")
    kw = None
    if keyword not in (None, ""):
        if not isinstance(keyword, str):
            errors.append("keyword 必須是字串")
        else:
            kw = CTRL_RE.sub("", keyword).strip()
            if len(kw) > MAX_KEYWORD:
                errors.append(f"keyword 不可超過 {MAX_KEYWORD} 字")
            kw = kw or None
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        errors.append(f"limit 必須是 1–{MAX_LIMIT} 的整數")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        errors.append("offset 必須是不小於 0 的整數")
    if errors:
        log.add("條件驗證失敗：" + "；".join(errors))
        return blocked("條件未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "條件未通過驗證：" + "；".join(errors), errors)
    filters = {"role_view": view, "categories": cats, "start_date": sd, "end_date": ed, "keyword": kw, "limit": limit, "offset": offset}
    log.add(f"身分判定為「{'公開（一般民眾）' if view == 'public' else '內部'}」；條件：類別 {cats or '不限'}、"
            f"日期 {sd or '不限'} ～ {ed or '不限'}、關鍵字 {kw or '無'}、每頁 {limit} 筆、起點 {offset}。")

    # ---------- 2. 載入 ----------
    rows, warns = cat.all_rows()
    n_docs = sum(1 for r in rows if r["origin"] == "docs")
    n_imp = len(rows) - n_docs
    n_pub = sum(1 for r in rows if r["is_public"] == 1)
    log.add(f"載入 {len(rows)} 份文件的元資料：docs/ {n_docs} 份、匯入索引 {n_imp} 份；其中已宣告公開 {n_pub} 份。")

    # ---------- 3. 過濾 ----------
    pool = cat.visible_rows(rows, view)
    conn = cat.memory_db(pool)
    try:
        where, params = ["1=1"], []
        if cats:
            where.append("category IN (%s)" % ",".join("?" * len(cats)))
            params += cats
        if sd:
            where.append("updated_at >= ?")
            params.append(sd)
        if ed:
            where.append("updated_at <= ?")
            params.append(ed)
        if kw:
            like = "%" + cat.like_escape(kw) + "%"
            where.append("(source_name LIKE ? ESCAPE '\\' OR doc_id LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\' "
                         "OR content_preview LIKE ? ESCAPE '\\' OR search_text LIKE ? ESCAPE '\\')")
            params += [like] * 5
        wsql = " AND ".join(where)
        total = conn.execute(f"SELECT COUNT(*) FROM catalog WHERE {wsql}", params).fetchone()[0]
        facets = [{"category": c, "count": n} for c, n in conn.execute("SELECT category, COUNT(*) FROM catalog GROUP BY category ORDER BY category")]
        log.add(f"在可見的 {len(pool)} 份文件中以參數化 SQL（WHERE {len(where) - 1} 個條件）過濾，符合 {total} 份。"
                + ("公開身分只會看到 is_public=1 的文件。" if view == "public" else ""))

        # ---------- 4. 排序分頁 ----------
        cols = ["doc_id", "source_name", "category", "category_inferred", "updated_at", "license_type", "content_preview", "source_url",
                "char_count", "chunk_count", "origin", "is_public", "imported_at"]
        cur = conn.execute(f"SELECT {', '.join(cols)} FROM catalog WHERE {wsql} ORDER BY updated_at DESC, doc_id ASC LIMIT ? OFFSET ?",
                           params + [limit, offset])
        docs = [_row_dict(r, cols, view != "public") for r in cur.fetchall()]
        log.add(f"依 updated_at 由新到舊（同日以 doc_id）排序，取第 {offset + 1}–{offset + len(docs)} 筆（共 {total} 筆）。"
                if docs else f"排序後沒有可顯示的資料列（起點 {offset}，共 {total} 筆）。")
    finally:
        conn.close()

    # ---------- 5. 可見性核對 ----------
    if view == "public":
        leaked = [r["doc_id"] for r in pool if r["is_public"] != 1]
        if leaked:
            return blocked("可見性核對失敗", "BLOCKED_BY_GUARDRAIL (visibility check failed)", "內部錯誤：公開結果含有非公開文件，已攔截。")
    weak = sum(1 for d in docs if d["category_inferred"])
    warnings = list(warns)
    if view == "public" and n_pub == 0:
        warnings.append("目前沒有任何文件被宣告為公開。管理者需在 data/catalog_manifest.json 把確定可公開的文件標為 is_public: true")
    if weak:
        warnings.append(f"本頁有 {weak} 份文件的類別是依檔名推測（category_inferred），請在 manifest 補上正式類別")
    unlabeled = sum(1 for d in docs if d["license_type"] == "未標註")
    if unlabeled:
        warnings.append(f"本頁有 {unlabeled} 份文件尚未標註授權")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"可見性核對通過（{'每一列 is_public=1' if view == 'public' else '內部身分可見全部'}）。防呆檢核狀態：{guardrail}。")
    found = total > 0
    answer = (f"共 {total} 份文件符合條件，本頁顯示 {len(docs)} 份。" if found else
              ("查無符合條件的文件。" + ("目前沒有任何公開文件。" if view == "public" and n_pub == 0 else "請放寬類別、日期或關鍵字。")))
    return finish({"status": "success", "found": found, "documents": docs, "total": total, "returned": len(docs),
                   "categories_available": facets, "filters": filters, "warnings": warnings,
                   "guardrail_status": guardrail, "answer_text": answer})


def get_document_preview(doc_id, role="public", max_chunks=8) -> dict:
    """某份文件的切片預覽與出處。看不到的文件與不存在的文件回傳同樣訊息（不洩漏存在與否）。"""
    nf = {"status": "success", "found": False, "document": None, "chunks": [], "total_chunks": 0,
          "answer_text": "查無此文件，或您沒有檢視權限。"}
    view = cat.view_of_role(role) if isinstance(role, str) else None
    if view is None or not isinstance(doc_id, str) or not 0 < len(doc_id) <= 200 or isinstance(max_chunks, bool) \
            or not isinstance(max_chunks, int) or not 1 <= max_chunks <= 50:
        return nf
    rows, _ = cat.all_rows()
    r = next((x for x in cat.visible_rows(rows, view) if x["doc_id"] == doc_id), None)
    if r is None:
        return nf
    if r["origin"] == "docs":
        try:
            from .skill_27_kb_import_pipeline import sliding_windows
        except ImportError:
            from skill_27_kb_import_pipeline import sliding_windows
        text = r["_text"]
        chunks_all = sliding_windows(text, 500, 50) if text else []
        total = len(chunks_all)
        chunks = [{"seq": i, "text": t} for i, t in enumerate(chunks_all[:max_chunks])]
    else:
        from contextlib import closing
        total, chunks = 0, []
        with closing(kb.connect()) as conn:
            total = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()[0]
            chunks = [{"seq": s, "text": t} for s, t in conn.execute(
                "SELECT seq, text FROM chunks WHERE doc_id = ? ORDER BY seq LIMIT ?", (doc_id, max_chunks))]
    doc = {k: r[k] for k in PUBLIC_FIELDS}
    if view != "public":
        doc["is_public"] = bool(r["is_public"])
        doc["imported_at"] = r["imported_at"]
    doc["category_inferred"] = bool(r["category_inferred"])
    return {"status": "success", "found": True, "document": doc, "chunks": chunks, "total_chunks": total,
            "truncated": total > len(chunks), "answer_text": f"《{r['source_name']}》共 {total} 個切片，顯示前 {len(chunks)} 個。"}


if __name__ == "__main__":
    import json
    if "--init-manifest" in sys.argv:
        p, n = cat.init_manifest()
        print(f"已寫入 {p}（{n} 份文件，全部 is_public=false；請把確定可公開的改成 true 並補授權與出處）")
    else:
        r = query_document_catalog(role="public")
        print(json.dumps({k: v for k, v in r.items() if k != "steps"}, ensure_ascii=False, indent=2)[:2500])
