"""
skill_01_tool_regulation_search.py - 工具與公開法規檢索技能 (動態檔案讀取與無硬編碼版)

對應系統規格：US-01 / 01. 製造知識庫檢索與智慧問答頁面
演算法機制：動態掃描 docs/ 資料夾 -> TF-IDF 詞頻向量化 + 餘弦相似度 + KNN 排序 + Guardrail 防呆
"""

import json
import math
import os
import re
from collections import Counter


def search_tool_regulations(
    query_text: str = "",
    scope: str = "all",
    top_k: int = 3,
    threshold: float = 0.10,
    output_json_path: str = None
) -> dict:
    """
    動態掃描 docs/ 資料夾並進行智慧檢索的主函數
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 自動決定輸出 JSON 路徑
    if not output_json_path:
        output_json_path = os.path.join(current_dir, "..", "data", "tool_regulation_search_result.json")

    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)

    # 🛡️ 防呆檢核：如果沒有輸入查詢文字，直接回傳引導提示
    if not query_text or query_text.strip() == "":
        empty_result = {
            "status": "success",
            "found": False,
            "query": "",
            "scope": scope,
            "similarity_score": 0.0,
            "threshold": threshold,
            "answer_text": "請在檢索框輸入您想查詢的製造規範、SOP 或法規關鍵字。",
            "source_title": "等待輸入",
            "source_url": "",
            "search_results": [],
            "steps": []
        }
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(empty_result, f, ensure_ascii=False, indent=2)
        return empty_result

    steps_log = []

    # 1. 動態掃描與讀取 docs/ 資料夾底下的真實文件
    docs_dir = os.path.join(current_dir, "..", "docs")
    knowledge_base = []

    if os.path.exists(docs_dir):
        for filename in os.listdir(docs_dir):
            if filename.lower().endswith((".txt", ".md")):
                file_path = os.path.join(docs_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                    
                    doc_id = filename.rsplit(".", 1)[0]
                    category = "repairs" if "sop" in filename.lower() else "regulations"
                    
                    knowledge_base.append({
                        "doc_id": doc_id,
                        "category": category,
                        "source_title": filename,
                        "source_url": f"/docs/{filename}",
                        "content": file_content.strip()
                    })
                except Exception as e:
                    print(f"讀取檔案 {filename} 失敗: {e}")

    steps_log.append({
        "step_number": 1,
        "step_name": "動態掃描 docs/ 資料夾與載入檔案",
        "description": f"成功掃描目標路徑 '{docs_dir}'，動態載入 {len(knowledge_base)} 筆真實知識庫文件。",
        "skill_name": "skill_01_tool_regulation_search",
        "algorithm_used": "Dynamic Directory File Scanner",
        "package_used": "os, io"
    })

    # 範圍過濾
    filtered_kb = [item for item in knowledge_base if scope == "all" or item.get("category") == scope]
    if not filtered_kb:
        filtered_kb = knowledge_base

    # 2. 分詞與 Token 向量化
    def _tokenize(text: str) -> list:
        clean_text = re.sub(r'[^\w\s]', '', text.lower())
        tokens = re.findall(r'\w+', clean_text)
        bigrams = [
            clean_text[i:i+2] for i in range(len(clean_text) - 1)
            if not re.match(r'\s', clean_text[i:i+2])
        ]
        return tokens + bigrams

    query_tokens = _tokenize(query_text)
    steps_log.append({
        "step_number": 2,
        "step_name": "查詢字串 Token 向量化與分詞",
        "description": f"對查詢字串 '{query_text}' 進行正則清洗與 Bigram 切分，提取 {len(query_tokens)} 個特徵 Token。",
        "skill_name": "skill_01_tool_regulation_search",
        "algorithm_used": "Regular Expression Tokenization",
        "package_used": "re, collections"
    })

    # 3. 餘弦相似度 (Cosine Similarity) 計算
    search_results = []
    for doc in filtered_kb:
        doc_text = doc.get("source_title", "") + " " + doc.get("content", "")
        doc_tokens = _tokenize(doc_text)

        query_counter = Counter(query_tokens)
        doc_counter = Counter(doc_tokens)

        intersection = set(query_counter.keys()) & set(doc_counter.keys())
        dot_product = sum(query_counter[x] * doc_counter[x] for x in intersection)

        query_norm = math.sqrt(sum(v ** 2 for v in query_counter.values()))
        doc_norm = math.sqrt(sum(v ** 2 for v in doc_counter.values()))

        cosine_sim = (
            dot_product / (query_norm * doc_norm)
            if (query_norm > 0 and doc_norm > 0)
            else 0.0
        )

        search_results.append({
            "doc_id": doc.get("doc_id"),
            "category": doc.get("category"),
            "source_title": doc.get("source_title"),
            "source_url": doc.get("source_url"),
            "content": doc.get("content"),
            "similarity_score": round(cosine_sim, 4)
        })

    steps_log.append({
        "step_number": 3,
        "step_name": "餘弦相似度矩陣計算",
        "description": "計算動態載入之文件向量與查詢向量間之夾角餘弦值：cos(θ) = (A·B) / (||A||·||B||)。",
        "skill_name": "skill_01_tool_regulation_search",
        "algorithm_used": "Cosine Similarity",
        "package_used": "math, collections.Counter"
    })

    # 4. KNN Top-K 近鄰排序
    search_results.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_results = search_results[:top_k]
    max_score = top_results[0]["similarity_score"] if top_results else 0.0

    steps_log.append({
        "step_number": 4,
        "step_name": "KNN Top-K 近鄰排序擷取",
        "description": f"依餘弦相似度得分降冪排序，採用 K-Nearest Neighbors (K={top_k}) 擷取得分最高之 Top-{len(top_results)} 筆條文，最高相似度為 {max_score:.4f}。",
        "skill_name": "skill_01_tool_regulation_search",
        "algorithm_used": "K-Nearest Neighbors (KNN)",
        "package_used": "Python Built-in Sorting"
    })

    # 5. Guardrail 得分防呆門檻比對
    if max_score >= threshold and len(knowledge_base) > 0:
        found = True
        best_doc = top_results[0]
        answer_text = (
            f"依據《{best_doc['source_title']}》之規定：{best_doc['content']} "
            f"（相關條文匹配相似度指數為 {max_score:.2f}）。"
        )
        source_title = best_doc["source_title"]
        source_url = best_doc["source_url"]
        guardrail_status = f"PASSED (Score {max_score:.4f} >= Threshold {threshold})"
    else:
        found = False
        answer_text = (
            "查不到相關法規與案例資料。系統無法從目前 docs/ 資料夾收錄之真實文本中獲取足夠數據以回答此問題，"
            "請確認資料夾是否放置對應檔案或重新調整檢索關鍵字。"
        )
        source_title = "無引用來源"
        source_url = ""
        guardrail_status = f"BLOCKED_BY_GUARDRAIL (Score {max_score:.4f} < Threshold {threshold})"

    steps_log.append({
        "step_number": 5,
        "step_name": "Guardrail 得分防呆門檻比對與解答生成",
        "description": f"防呆檢核狀態：{guardrail_status}。門檻極限值：{threshold}。依據檢核結果自動輸出 Grounded 條文解答卡片或防呆提示。",
        "skill_name": "skill_01_tool_regulation_search",
        "algorithm_used": "Threshold-based Guardrail Evaluation",
        "package_used": "Python Control Flow"
    })

    # 6. 組裝 JSON 結構
    output_result = {
        "status": "success",
        "found": found,
        "query": query_text,
        "scope": scope,
        "similarity_score": max_score,
        "threshold": threshold,
        "answer_text": answer_text,
        "source_title": source_title,
        "source_url": source_url,
        "search_results": top_results if found else [],
        "steps": steps_log
    }

    # 7. 寫入 JSON 檔
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_result, f, ensure_ascii=False, indent=2)

    return output_result


if __name__ == "__main__":
    print("=== 測試 SKILL: skill_01_tool_regulation_search (動態讀取版) ===")
    res = search_tool_regulations(
        query_text="CNS 2779-1 規範的是什麼抽樣方案",
        threshold=0.10
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))