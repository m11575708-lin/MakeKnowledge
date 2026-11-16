# SKILL: skill_29_retrieval_quality_eval

**name**: `skill_29_retrieval_quality_eval`  
**description**: 檢索品質評估：用 20 題標準問答逐題呼叫 skill_01，計算 Top-3 命中率與 MRR@10，附信賴區間與隨機基準，並列出錯誤案例。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 維運與評估 |
| 對應故事 | US-19 |
| 網頁 | 04 維運評估 |
| 演算法 | Hit@3、MRR |
| 講義週次 | —（標準函式庫） |
| 呼叫順序 | 04 頁：skill_29（與 skill_28 並列） |
| 程式檔 | `skills/skill_29_retrieval_quality_eval.py` |
| 主函式 | `evaluate_retrieval_quality()` |
| MCP 工具名 | `skill_29_retrieval_quality_eval` |

---

## 1. 做什麼

**使用者**：管理者（確認問答品質好不好）

讀 `data/eval/gold_20.json` 的 20 題（每題有預期條文），逐題呼叫 skill_01。Hit@3 = 預期條文出現在前 3 名的題數 / 有效題數；MRR = (1/|Q|) Σ 1/rankᵢ（看前 10 名，沒找到記 0）。另給 Hit@3 的 Wilson 95% 信賴區間、MRR 的 bootstrap 95% 區間、隨機排序基準，以及「第 1 名就引用正確」的比例；未命中的題目分成「查無資料」與「偏離」兩類。

**程式內的演算法流程**：以標準問答集逐題呼叫 skill_01 -> 算 Hit@3 與 MRR -> 歸類錯誤案例 Hit@3 = 預期來源出現在前 3 名的題數 / 有效題數 MRR   = (1/|Q|) Σ 1/rank_i      （預期來源排第 rank_i 名；沒找到記 0）

---

## 2. 輸入

函式：`evaluate_retrieval_quality(top_k=3, threshold=0.1, gold_set=None, search_fn=None, mrr_cutoff=10, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `top_k` | Integer | 否 | `3` | 傳給 skill_01 的 K |
| `threshold` | Float | 否 | `0.1` | 傳給 skill_01 的門檻 |
| `gold_set` | String | 否 | `None` | 題庫路徑（預設 `data/eval/gold_20.json`） |
| `search_fn` | Function | 否 | `None` | 替換檢索函式（測試用；預設為 skill_01） |
| `mrr_cutoff` | Integer | 否 | `10` | MRR 只看前幾名 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `hit_rate_top3_pct` | Float | Top-3 命中率（%） | `70.0` |
| `hit_rate_top_k` | Integer | 命中率使用的 K | `3` |
| `mrr` | Float | MRR@10 | `0.6458` |
| `mrr_cutoff` | Integer | MRR 截斷名次 | `10` |
| `source_citation_correct_pct` | Float | 第 1 名就是預期條文的比例（%） | `55.0` |
| `hit_rate_ci95_pct` | Array | Hit@3 的 Wilson 95% 區間 | `[48.1, 85.5]` |
| `mrr_ci95` | Array | MRR 的 bootstrap 95% 區間 | `[0.4667, 0.8125]` |
| `random_baseline` | Object | 隨機排序基準 | `{"hit_rate_pct": 1.3, "mrr": 0.0125}` |
| `n_questions` | Integer | 題數 | `20` |
| `n_valid` | Integer | 有效題數 | `20` |
| `n_hits` | Integer | 命中題數 | `14` |
| `corpus_size` | Integer | 可檢索文件數 | `234` |
| `top_k` | Integer | 使用的 K | `3` |
| `threshold` | Float | 實際套用的門檻 | `0.1` |
| `gold` | Object | 題庫來源與是否自動產生 | `{"source": "file", "path": "data/eval/gold_20.json", "auto_generated":…}` |
| `error_summary` | Object | 錯誤類型統計 | `{"查無資料": 0, "偏離": 6}` |
| `error_cases_list` | Array | 未命中題目的問題、預期與實際排名 | `[{"qid": "Q01", "query": "危險性機械沒有檢查合格可以先拿來用嗎？", "expected": "…, …]`（共 6 筆） |
| `per_question` | Array | 逐題名次與分數 | `[{"qid": "Q01", "rank": null, "hit": false, "rr": 0.0, "top_s…, …]`（共 20 筆） |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `20 題評估：Top-3 命中率 70.0%、MRR@10 0.65，第 1 名引用正確來源 55.0%；6 題未命中。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |
| `generated_at` | String | 結果產生時間（ISO 8601） | `2026-11-16T22:44:07` |

---

## 4. 限制

1. 20 題是 Claude 依兩部法規草擬，須由使用者複核題意與預期條文；題數少，區間很寬（48.1–85.5%）。
2. 題庫檔不存在時會從文件句子自動產生題目，幾乎一定命中，只能檢查接線，結果會標示 auto_generated。
3. skill_01 只回傳通過門檻的名次，所以是 MRR@10，不是無截斷的 MRR。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `datetime` | Python 標準函式庫 | PSF License 2.0 | 日期處理 |
| `importlib` | Python 標準函式庫 | PSF License 2.0 | — |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| `statistics` | Python 標準函式庫 | PSF License 2.0 | 平均數、標準差 |
| `sys` | Python 標準函式庫 | PSF License 2.0 | 搜尋路徑 |
| 專案內模組 | — | 本專案 | `_common` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

以 3 題小例子手算 Hit@3 與 MRR 即可驗證公式。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 載入並驗證標準問答集 | 題庫來源：data/eval/gold_20.json；共 20 題、有效 20 題；語料 234 份文件；top_k=3、門檻 0.1、MRR 截斷 10。 | Gold-set Validation Guardrail | json, os, re |
| 2 | 逐題呼叫 skill_01 取回排名 | 對 20 題各呼叫一次 skill_01（TF-IDF 詞頻＋餘弦相似度＋KNN，Top-10）；20 題通過 Guardrail 門檻、0 題被判為查無資料。 | Retrieval via skill_01 (TF-IDF + Cosine + KNN) | skill_01_tool_regulation_search |
| 3 | 計算 Hit@3 與倒數排名 RR | 每題：預期來源排名 rank（以 doc_id／檔名比對，忽略大小寫與副檔名）；rank≤3 記命中；RR = 1/rank（rank>10 或未找到記 0）。14 題命中、6 題未命中。 | Hit@K and Reciprocal Rank | Python Built-in |
| 4 | 彙總 Hit@3、MRR 與信賴區間 | Hit@3 = 14/20 = 70.0%（Wilson 95% 區間 48.1–85.5%）；MRR@10 = mean(RR) = 0.6458（bootstrap 1000 次、種子 42，95% 區間 0.467–0.812）；第 1 名即為預期來源 11/20 = 55.0%。隨機排序基準：Hit@3 1.3%、MRR 0.013。 | Mean Reciprocal Rank + Wilson / Bootstrap CI | statistics, math, random |
| 5 | 錯誤案例歸類與品質判定 | 錯誤案例 6 題：查無資料 0 題（最高分低於門檻）、偏離 6 題（有結果但預期來源不在前 3 名）。防呆檢核狀態：PASSED。 | Error Categorisation + Baseline Guardrail | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_29_retrieval_quality_eval import evaluate_retrieval_quality
result = evaluate_retrieval_quality()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 20 題評估：Top-3 命中率 70.0%、MRR@10 0.65，第 1 名引用正確來源 55.0%；6 題未命中。

完整結果 JSON：`results/skill_29_retrieval_quality_eval_result.json`（2026-11-16 執行）。
