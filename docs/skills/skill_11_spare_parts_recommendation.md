# SKILL: skill_11_spare_parts_recommendation

**name**: `skill_11_spare_parts_recommendation`  
**description**: 備品推薦：以物品協同過濾（Item-based CF），依相似案例領用過的備品與備品間的共現關係推薦要準備的備品，並標出庫存狀態。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-07 |
| 網頁 | 08 案例與備品 |
| 演算法 | 物品協同過濾（Item-based CF） |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 08 頁：skill_10 → skill_09 → skill_11 |
| 程式檔 | `skills/skill_11_spare_parts_recommendation.py` |
| 主函式 | `recommend_spare_parts()` |
| MCP 工具名 | `skill_11_spare_parts_recommendation` |

---

## 1. 做什麼

**使用者**：設備維修工程師（出發維修前領備品）

建立「工單 × 備品」0/1 領用矩陣，備品相似度 sim(i,j) = co(i,j) / √(nᵢ·nⱼ)。以 skill_09 近鄰案例的相似度加權得到使用輪廓，推薦分數 score_j = Σ profileᵢ·sim(i,j) / Σ profileᵢ（0–1）；近鄰直接領用過的備品與常一起使用的備品都會得分。最後附上庫存標籤（OUT 缺料、LOW 偏低、NORMAL 正常）。

**程式內的演算法流程**：輸入防呆 -> 案例×備品領用矩陣 -> 備品間共現餘弦相似度 -> 以近鄰案例加權的使用輪廓計算推薦分數 -> 庫存與支持度 Guardrail

---

## 2. 輸入

函式：`recommend_spare_parts(case_id=None, neighbors=None, top_n=5, min_score=0.1, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `case_id` | String | 否 | `None` | 以單一工單為起點推薦（與 neighbors 擇一） |
| `neighbors` | Array[Object] | 否 | `None` | skill_09 的相似案例清單（含 case_id 與相似度） |
| `top_n` | Integer | 否 | `5` | 推薦幾項備品 |
| `min_score` | Float | 否 | `0.1` | 推薦分數下限 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "neighbors": [
    {
      "case_id": "MA-2024-089",
      "similarity": 1.0
    },
    {
      "case_id": "MA-2024-117",
      "similarity": 0.8407
    },
    {
      "case_id": "MA-2024-102",
      "similarity": 0.8096
    }
  ]
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `demo_cases (示範資料，非真實工單)` |
| `seed_cases` | Array | 作為起點的案例與權重 | `[{"case_id": "MA-2024-089", "weight": 1.0}, …]`（共 3 筆） |
| `recommended_parts` | Array | 推薦備品（料號、名稱、分數、來源、支持工單數、庫存、安全庫存、庫存狀態） | `[{"part_id": "SP-8821", "name": "馬達軸承 6309", "score": 0.6605,…, …]`（共 5 筆） |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["庫存偏低：SP-8822 冷卻風扇總成（2/3）"]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `建議備品 5 項，首選 SP-8821 馬達軸承 6309（推薦分數 0.66）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸入 `case_ids`（陣列），程式實際接受 `case_id`（單一）或 `neighbors`。


---

## 4. 限制

1. 工單與庫存是程式內建示範資料。
2. 推薦分數的算法刻意與講義不同：備品是 0/1 領用，套用講義的評分預測公式每個預測都會是 1，沒有鑑別力。
3. 支持工單數少的備品會加警語（目前 `PASSED_WITH_WARNINGS` 即為此原因）。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

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

對照 `cf.py itempredict`（講義第 6 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| 相似度 SP-8821–SP-8822 | 0.436436 | 0.436436 | 一致 | Skill 的「共現次數 ÷ √(nᵢnⱼ)」就是講義 0／1 評分表上的餘弦相似度 |
| 推薦分數的算法 | Σ 輪廓×相似度 ÷ Σ 輪廓（全部已用備品） | Σ 相似度×分數 ÷ Σ 相似度（最像的 k 個） 刻意不同：備品是 0／1 領用，套講義公式每個預測都是 1；Skill 首選 SP-8821 0.6605 | 算法不同 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 案例編號與近鄰權重防呆 | 近鄰案例 3 筆：MA-2024-089(權重 1.00)、MA-2024-117(權重 0.84)、MA-2024-102(權重 0.81)；top_n 與最低分數門檻皆合理。 | Boundary & Type Validation | math |
| 2 | 建立案例×備品領用矩陣 | 自 demo_cases (示範資料，非真實工單) 建立 16 筆案例 × 10 種備品的 0/1 領用矩陣；領用次數最多的備品：SP-8821（7 次）。 | Case-Part Usage Matrix | json, Python Built-in |
| 3 | 計算備品間共現餘弦相似度 | sim(i,j) = 共現次數 / √(nᵢ·nⱼ)，對所有備品配對計算（對角線為 1）。 | Item-based CF: Co-occurrence Cosine Similarity | math |
| 4 | 近鄰加權推薦分數計算 | 近鄰案例共領用 4 種備品，使用輪廓加總 6.30；score_j = Σ profile_i·sim(i,j) / Σ profile_i；最高分：SP-8821(0.66)、SP-8822(0.58)、SP-8850(0.56)。 | Weighted Item-based Collaborative Filtering | Python Built-in Sorting |
| 5 | 庫存與支持度 Guardrail 檢核 | 防呆檢核狀態：PASSED_WITH_WARNINGS。推薦 5 項（分數 ≥ 0.1）；缺料 0 項、庫存偏低 1 項。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_11_spare_parts_recommendation import recommend_spare_parts
result = recommend_spare_parts(neighbors=[{'case_id': 'MA-2024-089', 'similarity': 1.0}, {'case_id': 'MA-2024-117', 'similarity': 0.8407}, {'case_id': 'MA-2024-102', 'similarity': 0.8096}])
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 建議備品 5 項，首選 SP-8821 馬達軸承 6309（推薦分數 0.66）。

完整結果 JSON：`results/skill_11_spare_parts_recommendation_result.json`（2026-11-16 執行）。
