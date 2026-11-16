"""
_catalog.py - 文件目錄與「誰看得到哪些文件」的共用規則（skill_26、page01 檢索、page05 公開檢索共用）

文件有兩個來源：
  1. docs/ 資料夾的 .txt / .md —— skill_01 實際檢索的語料
  2. data/kb_index.sqlite 的 documents —— 由 skill_27 匯入的檔案（一律內部資料）

可見性（本專案唯一的公開／內部邊界，預設「不公開」）：
  * docs/ 的檔案只有在 data/catalog_manifest.json 明確寫 "is_public": true 才算公開；沒登記的一律內部。
    （檔名看起來像法規不代表可以公開，授權與出處必須由管理者宣告。）
  * 匯入的檔案 is_public 預設 0。
  * 公開身分（一般民眾）只看得到 is_public = 1 的文件；內部身分（工程師、管理者、廠長）看得到全部。

catalog_manifest.json 格式：
  {"documents": [{"file": "cns_2779.md", "source_name": "CNS 2779-1 …", "category": "CNS 標準", "updated_at": "2026-10-15",
                  "license_type": "政府資料開放授權 (OGDL v1.0)", "source_url": "https://…", "is_public": true}]}
  沒登記的欄位會有保守預設：category 依檔名推測（會標示 category_inferred）、updated_at 取檔案修改日、license「未標註」、source_url 空白。
  執行 `python skills/skill_26_document_catalog_query.py --init-manifest` 可產生範本（全部 is_public=false，不覆蓋既有檔案）。
"""

import importlib
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from ._common import project_root, save_json
    from . import _kb_store as kb
except ImportError:
    from _common import project_root, save_json
    import _kb_store as kb

PUBLIC_VIEWS = ("public",)
INTERNAL_ROLES = ("internal", "engineer", "admin", "viewer")
MAX_MANIFEST = 2000
MAX_DOC_BYTES = 2 * 1024 * 1024
SEARCH_TEXT_CHARS = 20000
FULL_TEXT_CHARS = 20000
URL_RE = re.compile(r"^https?://[^\s<>\"']{1,500}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CATEGORY_RULES = [
    (re.compile(r"cns", re.I), "CNS 標準"),
    (re.compile(r"osha|職安|安全衛生|勞檢|法規|law", re.I), "職安法規"),
    (re.compile(r"sop|維修|手冊|manual|repair", re.I), "設備維修手冊"),
    (re.compile(r"品質|製程|quality|process", re.I), "製程品質規範"),
]


def docs_dir() -> str:
    return os.path.join(project_root(), "docs")


def manifest_path() -> str:
    return os.path.join(project_root(), "data", "catalog_manifest.json")


def valid_date(s) -> bool:
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def infer_category(filename: str) -> str:
    for rx, name in CATEGORY_RULES:
        if rx.search(filename):
            return name
    return "未分類"


def _preview(text: str, n: int = 200) -> str:
    t = re.sub(r"\s+", " ", re.sub(r"^[#>*\-\s|]+", "", text, flags=re.M)).strip()
    return t[:n] + ("…" if len(t) > n else "")


def _cap(s, n):
    return s.strip()[:n] if isinstance(s, str) else ""


# ---------------------------------------------------------------- 來源 1：docs/
def load_manifest():
    """回傳 ({檔名: 條目}, warnings)。格式錯誤整份忽略（全部視為內部），並回報原因。"""
    p = manifest_path()
    if not os.path.isfile(p):
        return {}, []
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        return {}, [f"catalog_manifest.json 無法讀取（{e}），所有 docs/ 文件視為內部資料"]
    if isinstance(raw, dict):
        raw = raw.get("documents")
    if not isinstance(raw, list) or len(raw) > MAX_MANIFEST:
        return {}, ["catalog_manifest.json 格式不符（需為文件陣列，上限 2000 筆），所有 docs/ 文件視為內部資料"]
    out, warns = {}, []
    for i, e in enumerate(raw, 1):
        if not isinstance(e, dict) or not isinstance(e.get("file"), str):
            warns.append(f"manifest 第 {i} 筆缺少 file，已略過")
            continue
        fn = e["file"]
        if fn != os.path.basename(fn) or not fn.lower().endswith((".txt", ".md")):
            warns.append(f"manifest 第 {i} 筆的 file 不合法（只接受 docs/ 下的單純檔名）：{fn[:40]}")
            continue
        ent = {"source_name": _cap(e.get("source_name"), 200), "category": _cap(e.get("category"), 40),
               "license_type": _cap(e.get("license_type"), 120), "is_public": e.get("is_public") is True}
        if e.get("is_public") not in (True, False, None):
            warns.append(f"{fn}：is_public 必須是 true 或 false，已視為內部")
        ua = e.get("updated_at")
        if ua is not None:
            if valid_date(ua):
                ent["updated_at"] = ua
            else:
                warns.append(f"{fn}：updated_at 需為 YYYY-MM-DD，改用檔案修改日")
        url = e.get("source_url")
        if url:
            if isinstance(url, str) and URL_RE.match(url.strip()):
                ent["source_url"] = url.strip()
            else:
                warns.append(f"{fn}：source_url 只接受 http(s) 網址，已忽略")
        if ent["is_public"] and not ent["license_type"]:
            warns.append(f"{fn}：公開文件缺少 license_type（授權），請補上")
        out[fn] = ent
    return out, warns


def docs_rows():
    manifest, warns = load_manifest()
    rows, d = [], docs_dir()
    names = set()
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            fp = os.path.join(d, fn)
            if not (fn.lower().endswith((".txt", ".md")) and os.path.isfile(fp)) or os.path.islink(fp):
                continue
            try:
                if os.path.getsize(fp) > MAX_DOC_BYTES:
                    warns.append(f"{fn} 超過 {MAX_DOC_BYTES // 1048576}MB，未列入目錄")
                    continue
                with open(fp, "r", encoding="utf-8") as f:
                    text = f.read().strip()
            except (OSError, UnicodeDecodeError):
                warns.append(f"{fn} 無法以 UTF-8 讀取，未列入目錄")
                continue
            names.add(fn)
            m = manifest.get(fn, {})
            rows.append({
                "doc_id": fn.rsplit(".", 1)[0], "source_name": m.get("source_name") or fn,
                "category": m.get("category") or infer_category(fn), "category_inferred": not m.get("category"),
                "updated_at": m.get("updated_at") or datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d"),
                "license_type": m.get("license_type") or "未標註", "source_url": m.get("source_url", ""),
                "is_public": 1 if m.get("is_public") else 0, "content_preview": _preview(text),
                "search_text": text[:SEARCH_TEXT_CHARS], "char_count": len(text), "chunk_count": None,
                "origin": "docs", "imported_at": None, "_text": text,
            })
    for fn in manifest:
        if fn not in names:
            warns.append(f"manifest 登記的 {fn} 不在 docs/ 中，已忽略")
    return rows, warns


# ---------------------------------------------------------------- 來源 2：匯入索引
def _ro_connect():
    p = kb.db_path()
    if not os.path.isfile(p):
        return None
    return sqlite3.connect(Path(p).as_uri() + "?mode=ro", uri=True, timeout=5)


def import_rows():
    rows, warns = [], []
    try:
        conn = _ro_connect()
        if conn is None:
            return rows, warns
        try:
            for r in conn.execute(
                    "SELECT doc_id, source_name, category, updated_at, license_type, source_url, is_public, content_preview, "
                    "char_count, chunk_count, imported_at FROM documents"):
                rows.append({"doc_id": r[0], "source_name": r[1], "category": r[2], "category_inferred": False, "updated_at": r[3],
                             "license_type": r[4], "source_url": r[5] if URL_RE.match(r[5] or "") else "", "is_public": 1 if r[6] == 1 else 0,
                             "content_preview": r[7], "search_text": r[7], "char_count": r[8], "chunk_count": r[9],
                             "origin": "import", "imported_at": r[10]})
        finally:
            conn.close()
    except sqlite3.Error as e:
        warns.append(f"讀取匯入索引失敗：{e}")
    return rows, warns


def all_rows():
    a, w1 = docs_rows()
    b, w2 = import_rows()
    seen, rows = set(), []
    for r in a + b:
        if r["doc_id"] in seen:
            w1.append(f"文件編號 {r['doc_id']} 重複，只保留第一筆")
            continue
        seen.add(r["doc_id"])
        rows.append(r)
    return rows, w1 + w2


def visible_rows(rows, view):
    return [r for r in rows if view != "public" or r["is_public"] == 1]


def view_of_role(role):
    """'public' 或內部角色 → 'public' / 'internal'；其他值回傳 None（呼叫端應拒絕，不可預設放行）。"""
    if role == "public":
        return "public"
    if role in INTERNAL_ROLES:
        return "internal"
    return None


# ---------------------------------------------------------------- 目錄查詢（in-memory sqlite，參數化）
def memory_db(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE catalog (doc_id TEXT PRIMARY KEY, source_name TEXT, category TEXT, category_inferred INTEGER, "
                 "updated_at TEXT, license_type TEXT, source_url TEXT, is_public INTEGER, content_preview TEXT, search_text TEXT, "
                 "char_count INTEGER, chunk_count INTEGER, origin TEXT, imported_at TEXT)")
    conn.executemany("INSERT INTO catalog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     [(r["doc_id"], r["source_name"], r["category"], 1 if r["category_inferred"] else 0, r["updated_at"], r["license_type"],
                       r["source_url"], r["is_public"], r["content_preview"], r["search_text"], r["char_count"], r["chunk_count"],
                       r["origin"], r["imported_at"]) for r in rows])
    return conn


def like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- 範本
def init_manifest():
    """為 docs/ 內每個檔案產生一筆登記（全部 is_public=false）。不覆蓋既有檔案。回傳 (路徑, 筆數)。"""
    p = manifest_path()
    if os.path.exists(p):
        raise FileExistsError(f"{p} 已存在，不覆蓋")
    rows, _ = docs_rows()
    docs = [{"file": r["doc_id"] + (".md" if os.path.exists(os.path.join(docs_dir(), r["doc_id"] + ".md")) else ".txt"),
             "source_name": r["source_name"], "category": r["category"], "updated_at": r["updated_at"],
             "license_type": "", "source_url": "", "is_public": False} for r in rows]
    save_json({"_note": "把確定可以公開的文件改成 is_public: true，並填入 license_type（授權）與 source_url（官方出處網址）。未登記或 false 的文件只有內部人員看得到。",
               "documents": docs}, p)
    return p, len(docs)


# ---------------------------------------------------------------- 檢索（skill_01）加上可見性過濾
def load_search_fn():
    for dotted in ("skills.skill_01_tool_regulation_search", "skill_01_tool_regulation_search"):
        try:
            return importlib.import_module(dotted).search_tool_regulations
        except ImportError:
            continue
        except Exception as e:     # noqa: BLE001
            print(f"[catalog] 載入 {dotted} 失敗：{e}", file=sys.stderr)
            return None
    return None


def retrieve_visible(query_text, scope="all", view="public", top_k=3, threshold=0.10, types=None, save_path=None, search_fn=None):
    """
    以 skill_01 的 TF-IDF／餘弦／KNN 結果為基礎，只保留 view 看得到的文件，並以可見範圍重新做 Guardrail。
    為什麼要重做：skill_01 的 found、最高分、答案文字和步驟說明是針對 docs/ 全部文件算的，直接回給公開使用者
    會洩漏內部文件的內容與分數。這裡以 threshold=0 取回全部分數、過濾後再套用門檻，並改寫含有全域數字的步驟說明。
    """
    fn = search_fn or load_search_fn()
    if fn is None:
        return {"status": "error", "found": False, "steps": [], "search_results": [],
                "answer_text": "系統找不到 skill_01_tool_regulation_search，請確認檔案已放入 skills/ 資料夾。"}
    scratch = os.path.join(project_root(), "data", "_skill01_scratch_web.json")
    try:
        raw = fn(query_text=query_text, scope=scope, top_k=500, threshold=0.0, output_json_path=scratch)
    except TypeError:
        raw = fn(query_text=query_text, scope=scope, top_k=500, threshold=0.0)
    if not isinstance(raw, dict) or raw.get("status") == "error":
        return {"status": "error", "found": False, "steps": [], "search_results": [],
                "answer_text": (raw or {}).get("answer_text", "skill_01 回傳格式錯誤") if isinstance(raw, dict) else "skill_01 回傳格式錯誤"}

    rows, _ = all_rows()
    vis = {r["doc_id"]: r for r in visible_rows(rows, view) if r["origin"] == "docs"}
    type_set = {t for t in (types or []) if isinstance(t, str)}
    hits = []
    for x in raw.get("search_results") or []:
        r = vis.get(x.get("doc_id"))
        if r is None or (type_set and r["category"] not in type_set):
            continue
        full = (r["_text"] if "_text" in r else x.get("content") or "")[:FULL_TEXT_CHARS]
        hits.append({"doc_id": r["doc_id"], "regulation_id": r["doc_id"], "source_title": r["source_name"], "title": r["source_name"],
                     "category": r["category"], "summary": _preview(full, 160), "content": full, "source_url": r["source_url"],
                     "license_type": r["license_type"], "similarity_score": x.get("similarity_score", 0.0)})
    hits.sort(key=lambda h: h["similarity_score"], reverse=True)
    top = hits[:max(1, int(top_k))]
    max_score = top[0]["similarity_score"] if top else 0.0
    n_vis = len([r for r in vis.values() if not type_set or r["category"] in type_set])

    if query_text and top and max_score >= threshold:
        top = [h for h in top if h["similarity_score"] >= threshold]      # 低於門檻的不當作「相關條文」列出
        found, best = True, top[0]
        guardrail = f"PASSED (Score {max_score:.4f} >= Threshold {threshold})"
        snippet = best["content"][:400] + ("…" if len(best["content"]) > 400 else "")
        answer = f"依據《{best['source_title']}》之規定：{snippet}（相關條文匹配相似度指數為 {max_score:.2f}）。"
        title, url = best["source_title"], best["source_url"]
    else:
        found, top = False, []
        guardrail = f"BLOCKED_BY_GUARDRAIL (Score {max_score:.4f} < Threshold {threshold})"
        answer = "查不到相關法規與案例資料。目前可檢索的文件中沒有足夠相符的內容，請調整關鍵字後再試。"
        title, url = "無引用來源", ""

    label = "公開文件" if view == "public" else "全部文件"
    steps = [dict(s) for s in raw.get("steps") or []]
    for s in steps:
        n = s.get("step_number")
        if n == 1:
            s["description"] = f"已掃描 docs/ 資料夾並載入知識庫文件；本次可檢索範圍（{label}）共 {n_vis} 份。"
        elif n == 4:
            s["description"] = (f"依餘弦相似度得分降冪排序，在可檢索範圍 {n_vis} 份文件內採用 K-Nearest Neighbors (K={top_k}) "
                                f"擷取 Top-{len(top) if found else len(hits[:top_k])}，最高相似度為 {max_score:.4f}。")
        elif n == 5:
            s["description"] = f"防呆檢核狀態：{guardrail}。門檻極限值：{threshold}。依據檢核結果輸出條文解答或防呆提示。"
    result = {"status": "success", "found": found, "query": query_text, "scope": scope, "view": view, "similarity_score": max_score,
              "threshold": threshold, "guardrail_status": guardrail, "answer_text": answer, "source_title": title, "source_url": url,
              "search_results": top, "n_searchable": n_vis, "steps": steps}
    if save_path:
        save_json(result, save_path)
    return result
