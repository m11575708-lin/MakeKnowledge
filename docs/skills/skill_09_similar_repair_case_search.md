# SKILL: skill_09_similar_repair_case_search

**name**: `skill_09_similar_repair_case_search`  
**description**: 相似維修案例檢索：以加權歐氏距離（KNN）在歷史工單中找出與目前故障特徵最像的 Top-3 案例。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-06 |
| 網頁 | 08 案例與備品 |
| 演算法 | KNN（加權歐氏距離） |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 08 頁：skill_10 → skill_09 → skill_11 |
| 程式檔 | `skills/skill_09_similar_repair_case_search.py` |
| 主函式 | `search_similar_repair_cases()` |
| MCP 工具名 | `skill_09_similar_repair_case_search` |

---

## 1. 做什麼

**使用者**：設備維修工程師（遇到故障想知道以前怎麼修）

把振動、溫度、壓力以整個案例庫的平均與標準差標準化，計算 d = √(mean(wᵢ·(z_查詢ᵢ − z_案例ᵢ)²))，權重 w 由 skill_10 依故障碼校正；相似度 = 1 / (1 + d)。依相似度取 Top-K，最高相似度低於門檻時回「查不到相似案例」。

**程式內的演算法流程**：輸入防呆 -> 案例庫載入與 Z-Score 標準化 -> 加權歐氏距離 -> KNN Top-K 排序 -> 相似度門檻 Guardrail

---

## 2. 輸入

函式：`search_similar_repair_cases(feature_vector=None, top_k=3, weights=None, error_code=None, restrict_to_error_code=False, min_similarity=0.3, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `feature_vector` | Array[Float] | 是 | — | `[振動 mm/s, 溫度 °C, 壓力 MPa]` |
| `top_k` | Integer | 否 | `3` | 回傳前幾名 |
| `weights` | Array[Float] | 否 | `None` | 三個特徵的距離權重（通常來自 skill_10）；未提供時全為 1 |
| `error_code` | String | 否 | `None` | 故障碼，用於標示同碼案例 |
| `restrict_to_error_code` | Boolean | 否 | `False` | 是否只在同一故障碼的案例中搜尋 |
| `min_similarity` | Float | 否 | `0.3` | Guardrail 門檻，最高相似度低於此值回查不到 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "feature_vector": [
    2.8,
    75.0,
    1.8
  ],
  "top_k": 3,
  "weights": [
    0.8812,
    0.1652,
    1.9536
  ],
  "error_code": "E-8021",
  "restrict_to_error_code": false
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `feature_vector` | Array | 實際使用的特徵向量 | `[2.8, 75.0, 1.8]` |
| `error_code` | String | 故障碼（由 skill_10 傳入） | `E-8021` |
| `top_k` | Integer | 實際的 K | `3` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `demo_cases (示範資料，非真實工單)` |
| `weights` | Array | 實際使用的距離權重（skill_10 校正後） | `[0.8812, 0.1652, 1.9536]` |
| `min_similarity` | Float | 相似度門檻 | `0.3` |
| `restricted_to_error_code` | Boolean | 是否只搜尋同故障碼案例 | `false` |
| `n_candidates` | Integer | 參與比對的候選案例數 | `16` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `top3_similar_cases` | Array | Top-K 案例（排名、工單號、相似度、距離、故障碼、設備、日期、處置說明） | `[{"rank": 1, "case_id": "MA-2024-089", "similarity": 1.0, "di…, …]`（共 3 筆） |
| `best_similarity` | Float | 第 1 名的相似度 | `1.0` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED (Best 1.0000 >= 0.3)` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `找到 3 筆相似歷史案例，最相似為 MA-2024-089（EQ-PRESS-01，馬達過熱，相似度 1.00）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 案例庫是程式內建的 16 筆示範工單（`demo_cases`），不是真實工單。
2. 距離是講義歐氏距離加上特徵權重再除以 √維度數（本 Skill 的設計），數值與講義原式不同但排名一致。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| 專案內模組 | — | 本專案 | `_common`, `_repair_data` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `knn.py dist`（講義第 6 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| MA-2024-089 距離 | 0.0 | 0.0 | 一致 | 講義的歐氏距離，加上 Skill 的特徵權重並除以 √維度數（Skill 的設計） |
| MA-2024-117 距離 | 0.1894 | 0.1894 | 一致 | 講義的歐氏距離，加上 Skill 的特徵權重並除以 √維度數（Skill 的設計） |
| MA-2024-102 距離 | 0.2352 | 0.2352 | 一致 | 講義的歐氏距離，加上 Skill 的特徵權重並除以 √維度數（Skill 的設計） |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 特徵向量、K 值與權重防呆 | 特徵向量 3 維皆為合理範圍內的有限數值；K=3；權重（平均 1）：[0.881, 0.165, 1.954]；最低相似度門檻 0.3。 | Boundary & Type Validation | math |
| 2 | 載入案例庫並 Z-Score 標準化 | 自 demo_cases (示範資料，非真實工單) 載入 16 筆案例，以全案例庫的 μ、σ 標準化；候選 16 筆。查詢向量 z：vibration=-0.39；temperature=+0.90；pressure=-0.03。 | Z-Score Standardization | json, math |
| 3 | 加權歐氏距離計算 | 對每筆候選案例計算 d = √(mean(wᵢ·(z查詢ᵢ − z案例ᵢ)²))，並換算 similarity = 1/(1+d)。 | Weighted Euclidean Distance | math |
| 4 | KNN Top-K 近鄰排序擷取 | 依距離升冪排序，取 Top-3：MA-2024-089(d=0.000)、MA-2024-117(d=0.189)、MA-2024-102(d=0.235)。 | K-Nearest Neighbors (KNN) | Python Built-in Sorting |
| 5 | 相似度門檻 Guardrail 檢核與結果生成 | 防呆檢核狀態：PASSED (Best 1.0000 >= 0.3)。查詢參數皆在案例庫範圍內。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_09_similar_repair_case_search import search_similar_repair_cases
result = search_similar_repair_cases(feature_vector=[2.8, 75.0, 1.8], top_k=3, weights=[0.8812, 0.1652, 1.9536], error_code='E-8021', restrict_to_error_code=False)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED (Best 1.0000 >= 0.3)`）：

> 找到 3 筆相似歷史案例，最相似為 MA-2024-089（EQ-PRESS-01，馬達過熱，相似度 1.00）。

完整結果 JSON：`results/skill_09_similar_repair_case_search_result.json`（2026-11-16 執行）。
