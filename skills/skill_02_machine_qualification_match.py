"""
skill_02_machine_qualification_match.py - 機械設備與操作資格比對技能

對應系統規格：US-02 / 01. 製造知識庫檢索 / 05. 公開法規與商品檢驗查詢頁
演算法機制：設備類別過濾 -> Bigram 正規化 -> Jaccard 集合相似度 -> KNN Top-K 排序 -> Guardrail 防呆

規範資料來源：
  1. 優先讀取 data/qualification_rules.json（請放入由官方法規整理的正式條文）
  2. 若檔案不存在，退回內建「示範資料」(DEFAULT_RULES)，僅供功能展示，不是正式法條。

qualification_rules.json 格式（list）：
  [{"regulation_id": "...", "equipment_type": "...", "title": "...", "summary": "...",
    "required_credentials": ["..."], "keywords": ["..."], "source_url": "..."}]
"""

import json
import os
import re

try:
    from ._common import StepLog, default_output_path, save_json
except ImportError:  # 直接以腳本執行或放在專案根目錄時
    from _common import StepLog, default_output_path, save_json

SKILL_NAME = "skill_02_machine_qualification_match"

PLAN = [
    ("規範資料載入與設備類別過濾", "Metadata Filtering", "json, os"),
    ("查詢字串與資格集合正規化", "Bigram Tokenization & Set Normalization", "re"),
    ("Jaccard 集合相似度計算", "Jaccard Similarity", "Python set"),
    ("KNN Top-K 近鄰排序擷取", "K-Nearest Neighbors (KNN)", "Python Built-in Sorting"),
    ("Guardrail 得分防呆門檻比對與解答生成", "Threshold-based Guardrail Evaluation", "Python Control Flow"),
]

# 資格集合與文字相似度的加權（無查詢文字時，資格集合權重為 1.0）
W_CREDENTIAL = 0.6
W_TEXT = 0.4

DEFAULT_RULES = [
    {
        "regulation_id": "OSH-PRESS-01",
        "equipment_type": "衝壓剪切機械",
        "title": "衝壓機械操作人員資格（示範資料）",
        "summary": "衝壓機操作人員須為專任操作人員，並完成相關安全教育訓練、取得結業證書後方得操作。",
        "required_credentials": ["專任操作人員", "教育訓練結業證書"],
        "keywords": ["衝壓機", "操作人員", "資格", "教育訓練", "結業證書"],
        "source_url": "",
    },
    {
        "regulation_id": "OSH-PRESS-02",
        "equipment_type": "衝壓剪切機械",
        "title": "衝壓機械每日作業前安全檢點（示範資料）",
        "summary": "衝壓機操作人員於每日作業開始前，須檢點離合器、煞車、安全裝置及防護設施，並記錄備查。",
        "required_credentials": ["專任操作人員", "每日作業前檢點"],
        "keywords": ["衝壓機", "操作人員", "每日", "作業前", "安全檢點", "規定"],
        "source_url": "",
    },
    {
        "regulation_id": "OSH-LIFT-01",
        "equipment_type": "升降機具",
        "title": "升降機具操作人員資格與定期檢查（示範資料）",
        "summary": "升降機具操作人員須持有訓練合格證，且設備須通過定期檢查並取得合格證。",
        "required_credentials": ["操作人員訓練合格證", "定期檢查合格證"],
        "keywords": ["升降機", "操作人員", "資格", "定期檢查", "合格證"],
        "source_url": "",
    },
    {
        "regulation_id": "CNS-PT-01",
        "equipment_type": "電動工具",
        "title": "手持式電動工具使用與檢驗（示範資料）",
        "summary": "手持式電動工具須貼有商品檢驗標識，並通過絕緣電阻測試後方可使用。",
        "required_credentials": ["商品檢驗標識", "絕緣電阻測試合格"],
        "keywords": ["電動工具", "檢驗", "絕緣", "安全", "標識"],
        "source_url": "",
    },
]


def jaccard(a, b) -> float:
    """J(A,B) = |A ∩ B| / |A ∪ B|；兩集合皆空時回傳 0。"""
    set_a, set_b = set(a), set(b)
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _bigrams(text: str) -> set:
    clean = re.sub(r"[^\w]", "", (text or "").lower())
    if len(clean) < 2:
        return set(clean)
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def _normalize_credentials(items) -> list:
    if not items:
        return []
    if isinstance(items, str):
        items = [items]
    return sorted({str(x).strip().lower() for x in items if str(x).strip()})


def _load_rules():
    """回傳 (rules, source_label)。"""
    path = default_output_path("qualification_rules.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                rules = json.load(f)
            required = {"regulation_id", "equipment_type", "title", "summary", "required_credentials"}
            if isinstance(rules, list) and rules and all(required <= set(r) for r in rules):
                return rules, "data/qualification_rules.json"
            print("qualification_rules.json 格式不符，改用內建示範資料", flush=True)
        except Exception as e:
            print(f"讀取 qualification_rules.json 失敗：{e}，改用內建示範資料", flush=True)
    return DEFAULT_RULES, "內建示範資料 (DEFAULT_RULES)"


def _type_matches(rule_type: str, wanted: str) -> bool:
    return rule_type == wanted or (wanted and (wanted in rule_type or rule_type in wanted))


def match_machine_qualification(
    equipment_type: str = "衝壓剪切機械",
    user_credentials=None,
    query_text: str = "",
    top_k: int = 3,
    threshold: float = 0.20,
    output_json_path: str = None,
) -> dict:
    out_path = output_json_path or default_output_path("machine_qualification_match_result.json")
    log = StepLog(SKILL_NAME, PLAN)

    equipment_type = (equipment_type or "").strip()
    query_text = (query_text or "").strip()
    creds = _normalize_credentials(user_credentials)

    # 1. 載入規範並依設備類別過濾
    rules, source = _load_rules()
    candidates = [r for r in rules if _type_matches(r["equipment_type"], equipment_type)]
    supported = sorted({r["equipment_type"] for r in rules})
    log.add(
        f"自 {source} 載入 {len(rules)} 筆規範，依設備類別『{equipment_type or '(未指定)'}』"
        f"過濾後剩 {len(candidates)} 筆。"
    )

    base = {
        "status": "success",
        "equipment_type": equipment_type,
        "user_credentials": list(user_credentials or []),
        "query": query_text,
        "threshold": threshold,
        "data_source": source,
    }

    def finish(result: dict) -> dict:
        result["steps"] = log.steps
        save_json(result, out_path)
        return result

    # Guardrail A：查無該設備類別
    if not candidates:
        log.skip_to_last("查無對應設備類別之規範")
        guardrail = "BLOCKED_BY_GUARDRAIL (unknown equipment_type)"
        log.add(f"防呆檢核狀態：{guardrail}。目前支援類別：{'、'.join(supported)}。")
        return finish({
            **base,
            "found": False,
            "matched_qualification": None,
            "jaccard_score": 0.0,
            "guardrail_status": guardrail,
            "answer_text": f"查不到設備類別『{equipment_type}』之資格規範。目前支援：{'、'.join(supported)}。",
            "source_title": "無引用來源",
            "source_url": "",
            "search_results": [],
        })

    # 2. 正規化
    query_grams = _bigrams(query_text)
    use_text = bool(query_grams)
    w_cred, w_text = (W_CREDENTIAL, W_TEXT) if use_text else (1.0, 0.0)
    log.add(
        f"使用者資格 {len(creds)} 項（去空白、轉小寫、去重）；查詢字串切出 {len(query_grams)} 個 Bigram。"
        f"權重：資格集合 {w_cred}、文字 {w_text}"
        + ("" if use_text else "（未提供查詢文字，僅以資格集合比對）。")
    )

    # 3. Jaccard
    scored = []
    for r in candidates:
        required = _normalize_credentials(r["required_credentials"])
        cred_j = jaccard(creds, required)
        rule_text = " ".join([r["title"], r["summary"], " ".join(r.get("keywords", [])),
                              " ".join(r["required_credentials"])])
        text_j = jaccard(query_grams, _bigrams(rule_text)) if use_text else 0.0
        combined = w_cred * cred_j + w_text * text_j
        scored.append({
            "regulation_id": r["regulation_id"],
            "title": r["title"],
            "summary": r["summary"],
            "equipment_type": r["equipment_type"],
            "required_credentials": r["required_credentials"],
            "matched_credentials": sorted(set(creds) & set(required)),
            "missing_credentials": [c for c in r["required_credentials"]
                                    if c.strip().lower() not in set(creds)],
            "credential_jaccard": round(cred_j, 4),
            "text_jaccard": round(text_j, 4),
            "jaccard_score": round(combined, 4),
            "source_url": r.get("source_url", ""),
        })
    log.add("對每筆候選規範計算 J(A,B)=|A∩B|/|A∪B|：資格集合 Jaccard 與 Bigram 文字 Jaccard，"
            "再以加權和得到最終 jaccard_score。")

    # 4. KNN Top-K
    scored.sort(key=lambda x: x["jaccard_score"], reverse=True)
    top = scored[:max(1, int(top_k))]
    best = top[0]
    log.add(f"依 jaccard_score 降冪排序，K={top_k} 擷取 Top-{len(top)}；最高分為 {best['regulation_id']}"
            f"（{best['jaccard_score']:.4f}）。")

    # 5. Guardrail
    if best["jaccard_score"] >= threshold:
        qualified = not best["missing_credentials"]
        guardrail = f"PASSED (Score {best['jaccard_score']:.4f} >= Threshold {threshold})"
        if qualified:
            verdict = "您提供的資格已涵蓋此規範要求。"
        else:
            verdict = f"尚缺資格：{'、'.join(best['missing_credentials'])}。"
        answer = f"最相符規範為《{best['title']}》（{best['regulation_id']}）：{best['summary']}{verdict}"
        log.add(f"防呆檢核狀態：{guardrail}。門檻：{threshold}。資格符合狀態：{'QUALIFIED' if qualified else 'MISSING_CREDENTIALS'}。")
        return finish({
            **base,
            "found": True,
            "matched_qualification": best["title"],
            "regulation_id": best["regulation_id"],
            "qualification_status": "QUALIFIED" if qualified else "MISSING_CREDENTIALS",
            "matched_credentials": best["matched_credentials"],
            "missing_credentials": best["missing_credentials"],
            "jaccard_score": best["jaccard_score"],
            "credential_jaccard": best["credential_jaccard"],
            "text_jaccard": best["text_jaccard"],
            "guardrail_status": guardrail,
            "answer_text": answer,
            "source_title": best["title"],
            "source_url": best["source_url"],
            "search_results": top,
        })

    guardrail = f"BLOCKED_BY_GUARDRAIL (Score {best['jaccard_score']:.4f} < Threshold {threshold})"
    log.add(f"防呆檢核狀態：{guardrail}。門檻：{threshold}。")
    return finish({
        **base,
        "found": False,
        "matched_qualification": None,
        "jaccard_score": best["jaccard_score"],
        "guardrail_status": guardrail,
        "answer_text": "查不到足夠相符的資格規範。請補充使用者資格或查詢關鍵字後再試。",
        "source_title": "無引用來源",
        "source_url": "",
        "search_results": [],
    })


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_02_machine_qualification_match ===")
    res = match_machine_qualification(
        equipment_type="衝壓剪切機械",
        user_credentials=["專任操作人員", "每日作業前檢點"],
        query_text="衝壓機操作人員資格與每日作業前安全檢點規定",
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
