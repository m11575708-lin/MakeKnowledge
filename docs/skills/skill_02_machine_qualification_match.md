# SKILL: skill_02_machine_qualification_match

**name**: `skill_02_machine_qualification_match`  
**description**: 危險性機械操作資格比對：把使用者已具備的資格與法規要求的資格當成集合，用 Jaccard 相似度找最相符的規範並列出缺少的資格。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 檢索 |
| 對應故事 | US-02 |
| 網頁 | 05 公開法規查詢 |
| 演算法 | KNN + Jaccard 集合相似度 |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 05 頁：skill_02（選機械類別時） |
| 程式檔 | `skills/skill_02_machine_qualification_match.py` |
| 主函式 | `match_machine_qualification()` |
| MCP 工具名 | `skill_02_machine_qualification_match` |

---

## 1. 做什麼

**使用者**：一般民眾、想確認自己能不能操作某種機械的人

依機械類別過濾規範，將「已具備資格」與每條規範的「要求資格」做 Jaccard 集合相似度（|A∩B| / |A∪B|），再加上查詢文字的 Bigram Jaccard，加權成綜合分數後取 Top-K；回傳最相符的規範、已符合與尚缺的資格清單。綜合分數低於門檻時回「查不到」。

**程式內的演算法流程**：設備類別過濾 -> Bigram 正規化 -> Jaccard 集合相似度 -> KNN Top-K 排序 -> Guardrail 防呆

---

## 2. 輸入

函式：`match_machine_qualification(equipment_type='衝壓剪切機械', user_credentials=None, query_text='', top_k=3, threshold=0.2, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `equipment_type` | String | 否 | `'衝壓剪切機械'` | 機械類別，例如 `衝壓剪切機械` |
| `user_credentials` | Array[String] | 否 | `None` | 使用者已具備的資格，例如 `["教育訓練結業證書"]` |
| `query_text` | String | 否 | `''` | 補充的文字描述（會以 Bigram 參與文字 Jaccard） |
| `top_k` | Integer | 否 | `3` | 回傳前幾名規範 |
| `threshold` | Float | 否 | `0.2` | Guardrail 門檻（0–1），綜合 Jaccard 低於此值回「查不到」 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "equipment_type": "衝壓剪切機械",
  "user_credentials": [
    "教育訓練結業證書"
  ]
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `equipment_type` | String | 實際查詢的機械類別 | `衝壓剪切機械` |
| `user_credentials` | Array | 使用者已具備的資格 | `["教育訓練結業證書"]` |
| `query` | String | 補充查詢文字 | `` |
| `threshold` | Float | 實際套用的門檻 | `0.2` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `內建示範資料 (DEFAULT_RULES)` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `matched_qualification` | String | 最相符的規範名稱 | `衝壓機械操作人員資格（示範資料）` |
| `regulation_id` | String | 規範代碼（例 `OSH-PRESS-01`） | `OSH-PRESS-01` |
| `qualification_status` | String | `QUALIFIED`（資格齊全）或 `MISSING_CREDENTIALS`（尚缺資格） | `MISSING_CREDENTIALS` |
| `matched_credentials` | Array | 已符合的資格 | `["教育訓練結業證書"]` |
| `missing_credentials` | Array | 尚缺的資格 | `["專任操作人員"]` |
| `jaccard_score` | Float | 綜合分數（資格 Jaccard 與文字 Jaccard 加權） | `0.5` |
| `credential_jaccard` | Float | 資格集合的 Jaccard | `0.5` |
| `text_jaccard` | Float | 查詢文字的 Bigram Jaccard | `0.0` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED (Score 0.5000 >= Threshold 0.2)` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `最相符規範為《衝壓機械操作人員資格（示範資料）》（OSH-PRESS-01）：衝壓機操作人員須為專任操作人員，並完成相關安全教育訓練、取得結…` |
| `source_title` | String | 規範標題 | `衝壓機械操作人員資格（示範資料）` |
| `source_url` | String | 規範來源連結 | `` |
| `search_results` | Array | Top-K 規範清單 | `[{"regulation_id": "OSH-PRESS-01", "title": "衝壓機械操作人員資格（示範資料）…, …]`（共 2 筆） |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸出 `missing_items`，程式實際用 `missing_credentials`。


---

## 4. 限制

1. 資格規範目前是程式內建的示範資料（`DEFAULT_RULES`），不是正式法條；放入 `data/qualification_rules.json` 後才會改用正式規範。
2. 資格名稱要字面一致才算符合（「結業證書」與「教育訓練結業證書」視為不同），沒有同義詞處理。
3. 結果只供參考，是否具備操作資格以主管機關認定為準。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| 專案內模組 | — | 本專案 | `_common` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

Jaccard 屬 D-3 的「3–5 筆小資料手算」，【待補：手算紀錄】。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 規範資料載入與設備類別過濾 | 自 內建示範資料 (DEFAULT_RULES) 載入 4 筆規範，依設備類別『衝壓剪切機械』過濾後剩 2 筆。 | Metadata Filtering | json, os |
| 2 | 查詢字串與資格集合正規化 | 使用者資格 1 項（去空白、轉小寫、去重）；查詢字串切出 0 個 Bigram。權重：資格集合 1.0、文字 0.0（未提供查詢文字，僅以資格集合比對）。 | Bigram Tokenization & Set Normalization | re |
| 3 | Jaccard 集合相似度計算 | 對每筆候選規範計算 J(A,B)=\|A∩B\|/\|A∪B\|：資格集合 Jaccard 與 Bigram 文字 Jaccard，再以加權和得到最終 jaccard_score。 | Jaccard Similarity | Python set |
| 4 | KNN Top-K 近鄰排序擷取 | 依 jaccard_score 降冪排序，K=3 擷取 Top-2；最高分為 OSH-PRESS-01（0.5000）。 | K-Nearest Neighbors (KNN) | Python Built-in Sorting |
| 5 | Guardrail 得分防呆門檻比對與解答生成 | 防呆檢核狀態：PASSED (Score 0.5000 >= Threshold 0.2)。門檻：0.2。資格符合狀態：MISSING_CREDENTIALS。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_02_machine_qualification_match import match_machine_qualification
result = match_machine_qualification(equipment_type='衝壓剪切機械', user_credentials=['教育訓練結業證書'])
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED (Score 0.5000 >= Threshold 0.2)`）：

> 最相符規範為《衝壓機械操作人員資格（示範資料）》（OSH-PRESS-01）：衝壓機操作人員須為專任操作人員，並完成相關安全教育訓練、取得結業證書後方得操作。尚缺資格：專任操作人員。

完整結果 JSON：`results/skill_02_machine_qualification_match_result.json`（2026-11-16 執行）。
