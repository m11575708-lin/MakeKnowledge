# SKILL: skill_24_preventive_maintenance_hierarchy

**name**: `skill_24_preventive_maintenance_hierarchy`  
**description**: 設備風險階層分群：以凝聚式階層分群把 18 台設備依故障率、MTBF、負載建立階層樹，並以共生相關係數檢查樹的品質。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-15 |
| 網頁 | 13 生產指數與維護 |
| 演算法 | 凝聚階層式分群 |
| 講義週次 | 第 7 週（延伸） |
| 呼叫順序 | 13 頁：skill_24 → skill_25 |
| 程式檔 | `skills/skill_24_preventive_maintenance_hierarchy.py` |
| 主函式 | `build_hierarchy()` |
| MCP 工具名 | `skill_24_preventive_maintenance_hierarchy` |

---

## 1. 做什麼

**使用者**：生產排程主管 / 廠長

輸入風險方向一致的標準化指標矩陣（MTBF 取負號，數值越大＝風險越高），計算歐氏距離矩陣，每次合併最近的兩群，以 Lance–Williams 公式更新群間距離（single / complete / average）。輸出合併歷程（scipy 慣例）、畫樹狀圖用的葉序，以及共生相關係數（< 0.7 會警告）。

**程式內的演算法流程**：輸入防呆 -> 歐氏距離矩陣 -> 凝聚法逐步合併最近兩群（Lance–Williams 更新） -> 樹的品質檢查 -> Guardrail

---

## 2. 輸入

函式：`build_hierarchy(equipment_risk_matrix=None, linkage='average', equipment_ids=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `equipment_risk_matrix` | Array[Array[Float]] | 是 | — | 每列一台設備的標準化風險指標 |
| `linkage` | String | 否 | `'average'` | 群間距離：`single`、`complete`、`average` |
| `equipment_ids` | Array[String] | 否 | `None` | 設備 ID（與矩陣列數相同） |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "equipment_risk_matrix": "<18x3 陣列>",
  "linkage": "average",
  "equipment_ids": "<18 筆設備 ID>"
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `linkage` | String | 使用的連結方式 | `average` |
| `n_items` | Integer | 設備數 | `18` |
| `n_indicators` | Integer | 風險指標數 | `3` |
| `equipment_ids` | Array | 設備 ID（與矩陣列順序相同） | `["EQ-PRESS-01", …]`（共 18 筆） |
| `merge_history` | Array | 合併歷程 [左節點, 右節點, 合併距離, 新群大小] | `[[8, 9, 0.172704, 2], …]`（共 17 筆） |
| `leaf_order` | Array | 樹狀圖的葉節點順序 | `[13, 15, 16, 17, 12, 14, 6, 8, 9, 7, 11, 1, 2, 3, 5, 0, 4, 10]` |
| `cophenetic_correlation` | Float | 共生相關係數 | `0.785` |
| `monotonic` | Boolean | 合併高度是否單調遞增（樹是否合法） | `true` |
| `distance_stats` | Object | 原始距離矩陣的最小、平均、最大值 | `{"min": 0.1727, "mean": 2.1472, "max": 5.3404}` |
| `max_merge_height` | Float | 最後一次合併的高度 | `3.047826` |
| `suggested_threshold` | Float | 建議的切樹門檻（給 skill_25） | `2.4426` |
| `risk_matrix` | Array | 實際使用的標準化風險矩陣 | `[[0.607536, 1.144827, 1.488283], …]`（共 18 筆） |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `18 台設備以 average 連結建立階層樹，最後合併高度 3.05，共生相關係數 0.78。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 設備資料是模擬的 18 台（衝壓、軋延、加熱區各 6 台）。
2. 未標準化的指標會讓尺度大的欄位（MTBF 數千小時）主導距離，會警告。
3. 不同連結方式會得到不同的樹；同一資料與連結方式結果固定。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| 專案內模組 | — | 本專案 | `_common`, `_equipment_data`, `_hier`, `_spc_data` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `kmeans.py hier`（講義第 7 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| 18 台的 17 次合併高度（average） | 最後 3 步 1.3052、1.8374、3.0478 | 最後 3 步 1.3052、1.8374、3.0478 | 一致 | 全部合併高度逐一比對相同 |
| 合併高度（single） | 最後一步 1.2433 | 最後一步 1.2433 | 一致 | 全部合併高度逐一比對相同 |
| 合併高度（complete） | 最後一步 5.3404 | 最後一步 5.3404 | 一致 | 全部合併高度逐一比對相同 |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 設備風險矩陣與連結法防呆 | 18 台設備 × 3 項風險指標，連結法 average；矩陣為矩形且皆為有限數值。 | Boundary & Type Validation | math |
| 2 | 計算歐氏距離矩陣 | 計算 153 組設備對的歐氏距離：最小 0.173、平均 2.147、最大 5.340。 | Euclidean Distance Matrix  d(i,j)=√Σ(x_i−x_j)² | math |
| 3 | 凝聚法逐步合併最近兩群 | 重複 17 次「找最近的兩群並合併」（average 連結）：第 1 次合併 EQ-ROLL-03 與 EQ-ROLL-04（距離 0.173），最後一次合併高度 3.048（所有設備併成一群）。 | Agglomerative Clustering (Lance–Williams update) | Python Built-in |
| 4 | 樹的品質檢查（單調性與共生相關） | 合併高度單調遞增（無倒退）；共生相關係數 = 0.785（越接近 1 越忠實保留原始距離）。 | Cophenetic Correlation & Monotonicity Check | math |
| 5 | 階層樹 Guardrail 檢核 | 防呆檢核狀態：PASSED。矩陣已標準化、合併高度單調、共生相關係數足夠。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
# ... 代表網頁 API 傳入的大型資料（矩陣、前一個 Skill 的結果），由該頁 API 從模擬資料或前一步產生
from skill_24_preventive_maintenance_hierarchy import build_hierarchy
result = build_hierarchy(equipment_risk_matrix=..., linkage='average', equipment_ids=...)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 18 台設備以 average 連結建立階層樹，最後合併高度 3.05，共生相關係數 0.78。

完整結果 JSON：`results/skill_24_preventive_maintenance_hierarchy_result.json`（2026-11-16 執行）。
