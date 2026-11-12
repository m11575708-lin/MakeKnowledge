"""
skill_29_retrieval_quality_eval.py - 檢索品質評估技能

對應系統規格：US-19 / 04. 製造知識庫維運與回答品質評估頁
機制（非課堂演算法）：以標準問答集逐題呼叫 skill_01 -> 算 Hit@3 與 MRR -> 歸類錯誤案例
    Hit@3 = 預期來源出現在前 3 名的題數 / 有效題數
    MRR   = (1/|Q|) Σ 1/rank_i      （預期來源排第 rank_i 名；沒找到記 0）

說明（請務必讀）：
  * 標準問答集：data/eval/gold_20.json（格式見 load_gold）。每題要有 qid、query、expected（文件的 doc_id 或檔名）。
    檔案不存在時，會從 docs/ 的文件「自動產生」題目——題目是文件本身的句子，所以幾乎一定找得到。
    這只能檢查「系統接線有沒有壞」，不能代表真實使用者提問的品質，結果會標為 auto_generated 並加警語。
    要得到有意義的數字，請自己寫 20 題真實會被問到的問題（用口語、不要直接抄條文）放進 gold_20.json。
  * 排名的取得：skill_01 只回傳通過門檻的 Top-K。Hit@3 看前 3 名；MRR 看前 mrr_cutoff（預設 10）名，
    名次超過截斷點或被 Guardrail 擋下（查無資料）記 0，所以這是 MRR@10，不是無截斷的 MRR。
  * 「引用正確來源」(source_citation_correct_pct) = 第 1 名就是預期來源的比例（skill_01 的回答引用第 1 名）。
  * 題數少時數字很不穩：同時給 Hit@3 的 Wilson 95% 信賴區間與 MRR 的 bootstrap 95% 區間（固定亂數種子，可重現），
    並給「隨機排序」基準（Hit@3 = 3/文件數）。文件數 ≤ 3 時，只要沒被 Guardrail 擋下 Hit@3 就必然命中，鑑別力很低，會加警語。
  * 預期來源不存在於目前的 docs/（題庫過期）的題目不計入分母，並列在警語中。
  * 呼叫 skill_01 時會指定獨立的暫存輸出檔（data/eval/_skill01_scratch.json），不會覆蓋 page01 讀的結果檔。
  * 只評估「檢索」（skill_01 的前半），不評估 AnythingLLM 產生的回答是否正確。
  * 結果存成 data/retrieval_quality_result.json。
"""

import importlib
import json
import math
import os
import random
import re
import statistics
import sys
from datetime import datetime

try:
    from ._common import StepLog, default_output_path, project_root, save_json
except ImportError:
    from _common import StepLog, default_output_path, project_root, save_json

SKILL_NAME = "skill_29_retrieval_quality_eval"
DEFAULT_GOLD_REL = os.path.join("data", "eval", "gold_20.json")
TARGET_QUESTIONS = 20
MAX_QUESTIONS = 100
MAX_QUERY_LEN = 200
MAX_GOLD_BYTES = 1024 * 1024
MRR_CUTOFF = 10
SCOPES = ("all", "regulations", "repairs")
BOOT_N = 1000
BOOT_SEED = 42

PLAN = [
    ("載入並驗證標準問答集", "Gold-set Validation Guardrail", "json, os, re"),
    ("逐題呼叫 skill_01 取回排名", "Retrieval via skill_01 (TF-IDF + Cosine + KNN)", "skill_01_tool_regulation_search"),
    ("計算 Hit@3 與倒數排名 RR", "Hit@K and Reciprocal Rank", "Python Built-in"),
    ("彙總 Hit@3、MRR 與信賴區間", "Mean Reciprocal Rank + Wilson / Bootstrap CI", "statistics, math, random"),
    ("錯誤案例歸類與品質判定", "Error Categorisation + Baseline Guardrail", "Python Control Flow"),
]


# ---------------------------------------------------------------- 載入 skill_01 與語料
def load_search_fn():
    """優先 skills/skill_01…，其次專案根目錄（與 app.py 的 _safe_skill 相同順序）。失敗回傳 None。"""
    for dotted in ("skills.skill_01_tool_regulation_search", "skill_01_tool_regulation_search"):
        try:
            return importlib.import_module(dotted).search_tool_regulations
        except ImportError:
            continue
        except Exception as e:     # noqa: BLE001
            print(f"[skill_29] 載入 {dotted} 失敗：{e}", file=sys.stderr)
            return None
    return None


def docs_dir_for(search_fn) -> str:
    """skill_01 讀的是『自己所在資料夾的上一層/docs』；用同一規則找出實際語料資料夾。"""
    try:
        mod = sys.modules.get(search_fn.__module__)
        here = os.path.dirname(os.path.abspath(mod.__file__))
        return os.path.abspath(os.path.join(here, "..", "docs"))
    except Exception:     # noqa: BLE001
        return os.path.join(project_root(), "docs")


def load_corpus(docs_dir: str) -> dict:
    """與 skill_01 相同規則：docs/ 下的 .txt/.md（UTF-8 讀得進來者）。回傳 {doc_id: {title, content}}。"""
    corpus = {}
    if os.path.isdir(docs_dir):
        for fn in sorted(os.listdir(docs_dir)):
            fp = os.path.join(docs_dir, fn)
            if fn.lower().endswith((".txt", ".md")) and os.path.isfile(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        corpus[fn.rsplit(".", 1)[0]] = {"title": fn, "content": f.read().strip()}
                except (OSError, UnicodeDecodeError):
                    continue
    return corpus


def _norm_id(s) -> str:
    s = str(s or "").strip().casefold()
    return re.sub(r"\.(md|txt)$", "", s)


# ---------------------------------------------------------------- 標準問答集
def _gold_path(rel):
    """只接受 data/ 底下的檔案（解析符號連結後仍須在 data/ 內）。回傳 (path, error)。"""
    base = os.path.realpath(os.path.join(project_root(), "data"))
    p = os.path.realpath(os.path.join(project_root(), rel if rel else DEFAULT_GOLD_REL))
    if os.path.commonpath([base, p]) != base:
        return None, "題庫檔必須放在 data/ 資料夾內"
    return p, None


def load_gold(rel=None):
    """
    讀 data/eval/gold_20.json。格式：
        {"auto_generated": false, "questions": [{"qid": "Q01", "query": "…", "expected": "文件 doc_id 或檔名", "scope": "all"}, …]}
    或直接是題目陣列。回傳 (items, meta, errors)；檔案不存在回傳 (None, {"missing": True}, [])。
    """
    p, err = _gold_path(rel)
    if err:
        return None, {}, [err]
    if not os.path.isfile(p):
        return None, {"missing": True, "path": os.path.relpath(p, project_root())}, []
    if os.path.getsize(p) > MAX_GOLD_BYTES:
        return None, {}, [f"題庫檔超過 {MAX_GOLD_BYTES // 1024}KB"]
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        return None, {}, [f"題庫檔不是有效的 JSON：{e}"]
    auto = False
    if isinstance(raw, dict):
        auto = raw.get("auto_generated") is True
        raw = raw.get("questions")
    if not isinstance(raw, list) or not raw:
        return None, {}, ["題庫需為非空的題目陣列（或含 questions 陣列的物件）"]
    if len(raw) > MAX_QUESTIONS:
        return None, {}, [f"題數 {len(raw)} 超過上限 {MAX_QUESTIONS}"]
    items, errors, seen = [], [], set()
    for i, q in enumerate(raw, 1):
        if not isinstance(q, dict):
            errors.append(f"第 {i} 題不是物件")
            continue
        qid, query, exp = q.get("qid"), q.get("query"), q.get("expected")
        scope = q.get("scope", "all")
        if not isinstance(qid, str) or not qid.strip() or len(qid) > 20:
            errors.append(f"第 {i} 題缺少有效的 qid（1–20 字）")
        elif qid in seen:
            errors.append(f"qid {qid} 重複")
        elif not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LEN:
            errors.append(f"{qid}：query 需為 1–{MAX_QUERY_LEN} 字的字串")
        elif not isinstance(exp, str) or not exp.strip():
            errors.append(f"{qid}：缺少 expected（預期來源的 doc_id 或檔名）")
        elif scope not in SCOPES:
            errors.append(f"{qid}：scope 只能是 {'、'.join(SCOPES)}")
        else:
            seen.add(qid)
            items.append({"qid": qid.strip(), "query": query.strip(), "expected": exp.strip(), "scope": scope})
    if errors:
        return None, {}, errors[:8]
    return items, {"path": os.path.relpath(p, project_root()), "auto_generated": auto, "source": "file"}, []


def autogen_gold(corpus: dict, n: int = TARGET_QUESTIONS):
    """從 docs/ 的文件各取一句中段句子當題目（確定性，無亂數）。這是自我一致性檢查，不是真實問題。"""
    ids = sorted(corpus)
    if len(ids) > n:
        ids = [ids[round(i * (len(ids) - 1) / (n - 1))] for i in range(n)]
    items = []
    for did in ids:
        sents = [re.sub(r"^[#>*\-\s|]+", "", s).strip() for s in re.split(r"[。！？!?\n]", corpus[did]["content"])]
        sents = [s for s in sents if 10 <= len(s) <= 60]
        if not sents:
            continue
        items.append({"qid": f"Q{len(items) + 1:02d}", "query": sents[len(sents) // 2], "expected": did, "scope": "all"})
    return items


def write_gold_template(corpus: dict = None):
    """把自動產生的題目寫成 data/eval/gold_20.json 讓你改成真實題目。不會覆蓋既有檔案。回傳 (路徑, 題數)。"""
    p, err = _gold_path(None)
    if err or os.path.exists(p):
        raise FileExistsError(err or f"{p} 已存在，不覆蓋")
    if corpus is None:
        corpus = load_corpus(docs_dir_for(load_search_fn()))
    items = autogen_gold(corpus)
    save_json({"auto_generated": True, "_note": "這是自動產生的範本：題目是文件本身的句子。請改成真實會被問到的問題，並把 auto_generated 改成 false。",
               "questions": items}, p)
    return p, len(items)


# ---------------------------------------------------------------- 統計
def wilson_interval(hits: int, n: int, z: float = 1.96):
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def bootstrap_mean_ci(values, n_boot=BOOT_N, seed=BOOT_SEED):
    rng = random.Random(seed)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def random_baseline(n_docs: int, k: int, cutoff: int):
    """文件均勻隨機排序、只有 1 份相關文件時：Hit@k = min(k,N)/N；MRR@cutoff = (Σ_{r=1..min(cutoff,N)} 1/r) / N。"""
    return min(k, n_docs) / n_docs, sum(1 / r for r in range(1, min(cutoff, n_docs) + 1)) / n_docs


# ---------------------------------------------------------------- 主函式
def evaluate_retrieval_quality(top_k: int = 3, threshold: float = 0.10, gold_set=None, search_fn=None,
                               mrr_cutoff: int = MRR_CUTOFF, output_json_path: str = None) -> dict:
    out_path = output_json_path or default_output_path("retrieval_quality_result.json")
    log = StepLog(SKILL_NAME, PLAN)
    generated_at = datetime.now().isoformat(timespec="seconds")

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        result["generated_at"] = generated_at
        save_json(result, out_path)
        return result

    def blocked(label, guardrail, message, warnings=None):
        log.skip_to_last(label)
        log.add(f"防呆檢核狀態：{guardrail}。")
        return finish({"status": "success", "found": False, "hit_rate_top3_pct": None, "mrr": None, "error_cases_list": [],
                       "per_question": [], "n_questions": 0, "n_valid": 0, "top_k": top_k if isinstance(top_k, int) else None,
                       "warnings": warnings or [message], "guardrail_status": guardrail, "answer_text": message})

    # ---------- 1. 驗證參數與題庫 ----------
    errors, warnings = [], []
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
        errors.append("top_k 必須是 1–10 的整數")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        errors.append("threshold 必須是 0–1 的數值")
    if isinstance(mrr_cutoff, bool) or not isinstance(mrr_cutoff, int) or not (isinstance(top_k, int) and top_k <= mrr_cutoff <= 50):
        errors.append("mrr_cutoff 必須是不小於 top_k、不超過 50 的整數")
    if errors:
        log.add("參數驗證失敗：" + "；".join(errors))
        return blocked("參數未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid input)", "參數未通過驗證：" + "；".join(errors), errors)

    search_fn = search_fn or load_search_fn()
    if search_fn is None:
        log.add("找不到 skill_01_tool_regulation_search，無法評估。")
        return blocked("找不到 skill_01", "BLOCKED_BY_GUARDRAIL (skill_01 unavailable)",
                       "找不到 skill_01_tool_regulation_search，請確認檔案已放入 skills/ 資料夾。")
    corpus = load_corpus(docs_dir_for(search_fn))
    if not corpus:
        log.add("docs/ 內沒有可讀的 .txt/.md 文件，沒有東西可以檢索。")
        return blocked("語料為空", "BLOCKED_BY_GUARDRAIL (empty corpus)",
                       "docs/ 資料夾內沒有可檢索的文件（.txt／.md），無法評估檢索品質。請先放入文件。")

    items, meta, gerr = load_gold(gold_set)
    if gerr:
        log.add("標準問答集驗證失敗：" + "；".join(gerr))
        return blocked("題庫未通過驗證", "BLOCKED_BY_GUARDRAIL (invalid gold set)", "標準問答集有問題：" + "；".join(gerr), gerr)
    if items is None and gold_set:
        msg = f"找不到指定的題庫檔 {gold_set}"
        log.add(msg)
        return blocked("題庫不存在", "BLOCKED_BY_GUARDRAIL (gold set not found)", msg)
    if items is None:
        items = autogen_gold(corpus)
        meta = {"path": None, "auto_generated": True, "source": "auto_generated"}
        warnings.append(f"找不到題庫檔 {DEFAULT_GOLD_REL}，已從 docs/ 自動產生 {len(items)} 題")
    if meta.get("auto_generated"):
        warnings.append("題目是文件本身的句子（自我一致性檢查）：命中率會被高估，只能確認接線沒壞，不能代表真實提問的品質")
    if not items:
        log.add("沒有任何可用題目（自動產生也失敗）。")
        return blocked("沒有題目", "BLOCKED_BY_GUARDRAIL (no questions)", "沒有可用的題目，請提供 data/eval/gold_20.json。")

    corpus_ids = {_norm_id(k): k for k in corpus}
    valid, stale = [], []
    for q in items:
        (valid if _norm_id(q["expected"]) in corpus_ids else stale).append(q)
    if stale:
        warnings.append("以下題目的預期來源不在目前的 docs/ 中，未計入分母：" + "、".join(f"{q['qid']}→{q['expected']}" for q in stale[:6])
                        + ("…" if len(stale) > 6 else ""))
    if not valid:
        log.add(f"{len(items)} 題的預期來源全都不在 docs/ 中，無法評估。")
        return blocked("題庫與文件不符", "BLOCKED_BY_GUARDRAIL (gold set does not match corpus)",
                       "題庫的預期來源全都不在目前的 docs/ 中，請更新題庫或文件。", warnings)
    if len({q["query"] for q in valid}) < len(valid):
        warnings.append("題庫內有重複的題目文字，會重複計分")
    if len(valid) != TARGET_QUESTIONS:
        warnings.append(f"有效題數 {len(valid)}（規格為 {TARGET_QUESTIONS} 題）")
    if len(valid) < 10:
        warnings.append(f"有效題數只有 {len(valid)}，信賴區間會非常寬，數字僅供參考")
    log.add(f"題庫來源：{'自動產生' if meta.get('source') == 'auto_generated' else meta.get('path')}；共 {len(items)} 題、有效 {len(valid)} 題；"
            f"語料 {len(corpus)} 份文件；top_k={top_k}、門檻 {threshold}、MRR 截斷 {mrr_cutoff}。")

    # ---------- 2. 逐題檢索 ----------
    scratch = os.path.join(project_root(), "data", "eval", "_skill01_scratch.json")
    rows = []
    for q in valid:
        try:
            res = search_fn(query_text=q["query"], scope=q["scope"], top_k=mrr_cutoff, threshold=float(threshold), output_json_path=scratch)
        except TypeError:
            log.add("skill_01 不接受 output_json_path 參數；為避免覆蓋 page01 的結果檔，停止評估。")
            return blocked("skill_01 版本不相容", "BLOCKED_BY_GUARDRAIL (skill_01 incompatible)",
                           "目前的 skill_01 不支援 output_json_path，評估會覆蓋 page01 的結果檔，已停止。請使用專案提供的 skill_01 版本。")
        except Exception as e:     # noqa: BLE001
            log.add(f"呼叫 skill_01 失敗：{e}")
            return blocked("skill_01 執行失敗", "BLOCKED_BY_GUARDRAIL (skill_01 error)", f"呼叫 skill_01 時發生錯誤：{e}")
        if not isinstance(res, dict) or res.get("status") == "error":
            msg = (res or {}).get("answer_text", "未知錯誤") if isinstance(res, dict) else "回傳格式錯誤"
            log.add(f"skill_01 回傳錯誤：{msg}")
            return blocked("skill_01 回傳錯誤", "BLOCKED_BY_GUARDRAIL (skill_01 error)", f"skill_01 回傳錯誤：{msg}")
        results = res.get("search_results") or []
        rows.append({"q": q, "found": bool(res.get("found")), "top_score": res.get("similarity_score"),
                     "results": [{"doc_id": r.get("doc_id"), "title": r.get("source_title"), "score": r.get("similarity_score")} for r in results]})
    n_found = sum(1 for r in rows if r["found"])
    log.add(f"對 {len(rows)} 題各呼叫一次 skill_01（TF-IDF 詞頻＋餘弦相似度＋KNN，Top-{mrr_cutoff}）；"
            f"{n_found} 題通過 Guardrail 門檻、{len(rows) - n_found} 題被判為查無資料。")

    # ---------- 3. 命中與倒數排名 ----------
    per_q, errs = [], []
    for r in rows:
        q, exp = r["q"], _norm_id(r["q"]["expected"])
        rank = next((i for i, x in enumerate(r["results"], 1) if _norm_id(x["doc_id"]) == exp or _norm_id(x["title"]) == exp), None)
        hit = rank is not None and rank <= top_k
        rr = 1.0 / rank if rank is not None and rank <= mrr_cutoff else 0.0
        per_q.append({"qid": q["qid"], "rank": rank, "hit": hit, "rr": round(rr, 4), "top_score": r["top_score"]})
        if not hit:
            actual = [f"{x['title']}（{x['score']}）" for x in r["results"][:top_k]]
            if not r["found"]:
                etype, actual_txt = "查無資料", f"查無資料（最高分 {r['top_score']} 低於門檻 {threshold}）"
            else:
                etype = "偏離"
                actual_txt = "、".join(actual) if actual else "（無結果）"
                if rank is not None:
                    actual_txt += f"；預期來源排第 {rank} 名"
            errs.append({"qid": q["qid"], "query": q["query"], "expected": q["expected"], "actual": actual_txt,
                         "actual_top": [x["title"] for x in r["results"][:top_k]], "expected_rank": rank, "error_type": etype,
                         "top_score": r["top_score"]})
    log.add("每題：預期來源排名 rank（以 doc_id／檔名比對，忽略大小寫與副檔名）；"
            f"rank≤{top_k} 記命中；RR = 1/rank（rank>{mrr_cutoff} 或未找到記 0）。"
            f"{sum(1 for p in per_q if p['hit'])} 題命中、{len(errs)} 題未命中。")

    # ---------- 4. 彙總 ----------
    n = len(per_q)
    hits = sum(1 for p in per_q if p["hit"])
    top1 = sum(1 for p in per_q if p["rank"] == 1)
    rrs = [p["rr"] for p in per_q]
    hit_rate, mrr = hits / n, statistics.mean(rrs)
    w_lo, w_hi = wilson_interval(hits, n)
    b_lo, b_hi = bootstrap_mean_ci(rrs)
    base_hit, base_mrr = random_baseline(len(corpus), top_k, mrr_cutoff)
    log.add(f"Hit@{top_k} = {hits}/{n} = {hit_rate * 100:.1f}%（Wilson 95% 區間 {w_lo * 100:.1f}–{w_hi * 100:.1f}%）；"
            f"MRR@{mrr_cutoff} = mean(RR) = {mrr:.4f}（bootstrap {BOOT_N} 次、種子 {BOOT_SEED}，95% 區間 {b_lo:.3f}–{b_hi:.3f}）；"
            f"第 1 名即為預期來源 {top1}/{n} = {top1 / n * 100:.1f}%。隨機排序基準：Hit@{top_k} {base_hit * 100:.1f}%、MRR {base_mrr:.3f}。")

    # ---------- 5. 錯誤歸類與判定 ----------
    n_none = sum(1 for e in errs if e["error_type"] == "查無資料")
    n_off = len(errs) - n_none
    if len(corpus) <= top_k:
        warnings.append(f"語料只有 {len(corpus)} 份文件、不超過 top_k={top_k}，只要沒被 Guardrail 擋下，Hit@{top_k} 必然命中，鑑別力很低；請看 MRR、第 1 名命中率與查無資料題數")
    elif hit_rate <= base_hit + 1e-9:
        warnings.append(f"Hit@{top_k} 沒有高於隨機排序基準（{base_hit * 100:.1f}%），檢索可能沒有發揮作用")
    if n_found == 0:
        warnings.append("所有題目都被判為查無資料：請檢查 docs/ 內容與 skill_01 的門檻設定")
    if len(corpus) > 3 and meta.get("source") == "file" and hit_rate == 1.0 and n < 20:
        warnings.append("題數不多且全數命中，不代表沒有弱點，請補充更刁鑽的題目")
    guardrail = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"
    log.add(f"錯誤案例 {len(errs)} 題：查無資料 {n_none} 題（最高分低於門檻）、偏離 {n_off} 題（有結果但預期來源不在前 {top_k} 名）。"
            f"防呆檢核狀態：{guardrail}。")

    answer = (f"{n} 題評估：Top-{top_k} 命中率 {hit_rate * 100:.1f}%、MRR@{mrr_cutoff} {mrr:.2f}，"
              f"第 1 名引用正確來源 {top1 / n * 100:.1f}%；{len(errs)} 題未命中。"
              + ("（題目為自動產生，僅檢查接線）" if meta.get("auto_generated") else ""))
    return finish({
        "status": "success", "found": True,
        "hit_rate_top3_pct": round(hit_rate * 100, 1), "hit_rate_top_k": top_k, "mrr": round(mrr, 4), "mrr_cutoff": mrr_cutoff,
        "source_citation_correct_pct": round(top1 / n * 100, 1),
        "hit_rate_ci95_pct": [round(w_lo * 100, 1), round(w_hi * 100, 1)], "mrr_ci95": [round(b_lo, 4), round(b_hi, 4)],
        "random_baseline": {"hit_rate_pct": round(base_hit * 100, 1), "mrr": round(base_mrr, 4)},
        "n_questions": len(items), "n_valid": n, "n_hits": hits, "corpus_size": len(corpus), "top_k": top_k, "threshold": threshold,
        "gold": {"source": meta.get("source"), "path": meta.get("path"), "auto_generated": bool(meta.get("auto_generated"))},
        "error_summary": {"查無資料": n_none, "偏離": n_off},
        "error_cases_list": errs, "per_question": per_q,
        "warnings": warnings, "guardrail_status": guardrail, "answer_text": answer,
    })


if __name__ == "__main__":
    if "--init-gold" in sys.argv:
        path, cnt = write_gold_template()
        print(f"已寫入 {path}（{cnt} 題，請改成真實題目）")
    else:
        r = evaluate_retrieval_quality()
        print(json.dumps({k: v for k, v in r.items() if k not in ("steps", "per_question")}, ensure_ascii=False, indent=2)[:3000])
