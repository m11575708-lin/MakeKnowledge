# SKILL: skill_07_risk_level_classification

**name**: `skill_07_risk_level_classification`  
**description**: 勝算比與風險燈號：把故障機率換算成勝算比 p/(1−p)，依門檻分成紅黃綠燈並給建議處置。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-04 |
| 網頁 | 07 故障風險評估 |
| 演算法 | 勝算比 + 燈號劃分（邏輯迴歸延伸） |
| 講義週次 | 第 5 週 |
| 呼叫順序 | 07 頁：skill_06 → skill_07 → skill_08 |
| 程式檔 | `skills/skill_07_risk_level_classification.py` |
| 主函式 | `classify_risk_level()` |
| MCP 工具名 | `skill_07_risk_level_classification` |

---

## 1. 做什麼

**使用者**：設備維修工程師

接收 skill_06 的故障機率，截斷到 (0, 1) 開區間避免除以 0，計算勝算比 Odds = p/(1−p) = e^(wᵀx+b) 與對數勝算，依門檻（預設 GREEN < 0.40 ≤ YELLOW < 0.70 ≤ RED）給燈號與建議處置。

**程式內的演算法流程**：機率與門檻防呆 -> 機率截斷 -> 勝算比 Odds = p/(1-p) = e^(wᵀx+b) -> 紅黃綠燈號劃分 -> 飽和機率 Guardrail

---

## 2. 輸入

函式：`classify_risk_level(failure_probability=None, yellow_threshold=0.4, red_threshold=0.7, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `failure_probability` | Float | 是 | — | 故障機率（0–1），通常來自 skill_06 |
| `yellow_threshold` | Float | 否 | `0.4` | 黃燈門檻 |
| `red_threshold` | Float | 否 | `0.7` | 紅燈門檻（需大於黃燈門檻） |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "failure_probability": 0.291
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `failure_probability` | Float | 輸入的故障機率 | `0.291` |
| `probability_used` | Float | 截斷後實際計算用的機率 | `0.291` |
| `odds_ratio` | Float | 勝算比 p/(1−p) | `0.4104` |
| `log_odds` | Float | 對數勝算 | `-0.8905` |
| `risk_level` | String | `GREEN` / `YELLOW` / `RED` | `GREEN` |
| `risk_label` | String | 燈號中文說明 | `綠燈：正常` |
| `recommended_action` | String | 建議處置 | `維持例行巡檢，持續監控警報次數與壓力。` |
| `thresholds` | Object | 實際套用的黃、紅燈門檻 | `{"yellow": 0.4, "red": 0.7}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `綠燈：正常。故障勝算比 0.41：故障發生的可能性僅為不發生的 0.41 倍。維持例行巡檢，持續監控警報次數與壓力。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 燈號門檻是示範值，應依實際停機成本調整；07 頁最後是否派工以 skill_08 的成本最佳門檻為準。
2. 規格書寫 Odds = e^(wᵀx)，但範例（p=0.84 → 5.25）其實是 p/(1−p)，本 Skill 採後者（含截距）。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| `statistics` | Python 標準函式庫 | PSF License 2.0 | 平均數、標準差 |
| 專案內模組 | — | 本專案 | `_common`, `_failure_model`, `skill_03_sensor_data_preprocessing`, `skill_04_equipment_rul_prediction` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

勝算比由 skill_06 的邏輯迴歸換算，對照結果見 skill_06。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

本 Skill 沒有獨立的比對列，說明見上。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 故障機率與燈號門檻防呆 | 故障機率 0.2910 為 [0,1] 內的有限數值；燈號門檻 黃 0.4 / 紅 0.7 設定合理。 | Boundary & Type Validation | math |
| 2 | 機率邊界截斷 | 為避免 p=0 或 p=1 時勝算比為 0 / 無限大，將機率截斷至 [1e-06, 0.999999]（本次無需截斷）。 | Probability Clipping [ε, 1-ε] | math |
| 3 | 勝算比與對數勝算計算 | Odds = p/(1-p) = 0.2910/0.7090 = 0.4104；對數勝算 ln(Odds) = -0.8905（即線性分數 z = wᵀx + b）。 | Odds Ratio  p/(1-p) = e^z | math |
| 4 | 紅黃綠風險燈號劃分 | 依門檻劃分：p=0.2910，黃 ≥ 0.4、紅 ≥ 0.7 → GREEN。 | Threshold Band Classification | Python Control Flow |
| 5 | 飽和機率 Guardrail 檢核與處置建議生成 | 防呆檢核狀態：PASSED。機率未飽和，勝算比可正常解讀。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_07_risk_level_classification import classify_risk_level
result = classify_risk_level(failure_probability=0.291)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 綠燈：正常。故障勝算比 0.41：故障發生的可能性僅為不發生的 0.41 倍。維持例行巡檢，持續監控警報次數與壓力。

完整結果 JSON：`results/skill_07_risk_level_classification_result.json`（2026-11-16 執行）。
