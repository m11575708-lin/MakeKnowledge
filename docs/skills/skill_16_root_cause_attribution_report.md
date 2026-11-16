# SKILL: skill_16_root_cause_attribution_report

**name**: `skill_16_root_cause_attribution_report`  
**description**: 品質異常根因報告：整合 skill_14 的判定與 skill_15 的重要度，依「重要度 × 這批的偏離程度」找出最可能的根因並給處置建議。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-09 |
| 網頁 | 10 品質根因分析 |
| 演算法 | 結果整合報告（啟發式歸因） |
| 講義週次 | —（標準函式庫） |
| 呼叫順序 | 10 頁：skill_14 → skill_15 → skill_16 |
| 程式檔 | `skills/skill_16_root_cause_attribution_report.py` |
| 主函式 | `build_root_cause_report()` |
| MCP 工具名 | `skill_16_root_cause_attribution_report` |

---

## 1. 做什麼

**使用者**：品質與製程工程師

偏離量 devᵢ = (xᵢ − 良品平均ᵢ) / 全體標準差ᵢ，歸因分數 = MDIᵢ × |devᵢ|，佔比 = 分數 / 總和。佔比最高者為根因，依偏高或偏低對應手寫的處置建議（例如「降低爐溫並校正熱電偶」）。

**程式內的演算法流程**：整合 skill_14（預測）與 skill_15（MDI 排序）-> 計算批次偏離量 -> 歸因分數 = 重要度 × |偏離 z| -> 根因判定與處置建議 -> Guardrail

---

## 2. 輸入

函式：`build_root_cause_report(batch_id=None, batch_params=None, n_trees=100, prediction=None, importance=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `batch_id` | String | 否 | `None` | 批次編號 |
| `batch_params` | Array[Float] | 否 | `None` | 批次製程參數；未提供時用 batch_id 的參數 |
| `n_trees` | Integer | 否 | `100` | 樹的數量（未提供 prediction / importance 時才會重算） |
| `prediction` | Object | 否 | `None` | skill_14 的結果；提供時不重算 |
| `importance` | Object | 否 | `None` | skill_15 的結果；提供時不重算 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "batch_id": "B-2026-10"
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `batch_id` | String | 批次編號 | `B-2026-10` |
| `batch_params` | Array | 批次製程參數 | `[189.5, 36.5, 16.3]` |
| `root_cause_feature` | String | 根因參數 | `temp` |
| `root_cause_label` | String | 根因參數中文名稱 | `加熱溫度` |
| `root_cause_direction` | String | 偏高或偏低 | `high` |
| `risk_score` | Float | 風險分數（來自 skill_14 的不良機率） | `0.9223` |
| `anomaly_detected` | Boolean | skill_14 是否判異常 | `true` |
| `action_recommendation` | String | 處置建議 | `降低加熱爐設定溫度，並確認熱電偶校正與爐溫均勻度` |
| `action_code` | String | 處置代碼 | `REDUCE_HEATING_TEMP` |
| `contributions` | Array | 各參數的偏離 z、重要度、歸因分數與佔比 | `[{"feature": "temp", "label": "加熱溫度", "unit": "°C", "value": …, …]`（共 3 筆） |
| `n_trees` | Integer | 隨機森林的樹數 | `100` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["「加熱溫度」占比僅 44%，並非壓倒性主因，「冷卻水流量」（41%）也需一併檢查", …]`（共 2 筆） |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `根因指向「加熱溫度」（歸因占比 44%，風險分數 0.92）。建議：降低加熱爐設定溫度，並確認熱電偶校正與爐溫均勻度。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 歸因邏輯是本專案設計的啟發式，不是標準演算法；只代表相關，不能證明因果（10 頁有標示）。
2. 處置建議是手寫的示範規則，須由製程工程師確認。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `hashlib` | Python 標準函式庫 | PSF License 2.0 | SHA-256 去重 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| 專案內模組 | — | 本專案 | `_common`, `_forest`, `_quality_data`, `_quality_model`, `skill_14_yield_rate_anomaly_detection`, `skill_15_feature_importance_ranking` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

歸因分數可用 contributions 中的 importance 與 deviation_z 直接相乘驗證。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 前置預測與重要度結果檢核 | 重新呼叫 skill_14 / skill_15。預估良率 7.8%、不良機率（風險分數）0.922、判定 QUALITY_ANOMALY（95/100 棵樹投異常）；MDI 排名第一為「加熱溫度」。 | Upstream Result Validation | math |
| 2 | 計算批次參數偏離量 | 以訓練集中「良品」的平均值為基準線，偏離 z = (本批數值 - 良品平均) / 全體標準差：加熱溫度 189.5°C（良品平均 179.6）→ z=+1.44；冷卻水流量 36.5L/min（良品平均 43.7）→ z=-1.41；軋延速度 16.3m/min（良品平均 15.0）→ z=+0.91。 | Z-Score Deviation from Good-batch Baseline | statistics |
| 3 | 計算歸因分數  重要度 × \|偏離\| | 歸因分數 = MDI 重要度 × \|偏離 z\|：加熱溫度 0.406×1.44=0.585（占 44%）；冷卻水流量 0.386×1.41=0.544（占 41%）；軋延速度 0.208×0.91=0.190（占 14%）。 | Importance-weighted Deviation Attribution | Python Built-in |
| 4 | 根因判定與處置建議 | 歸因占比最高者為「加熱溫度」（44%），本批數值偏高；對應處置規則 REDUCE_HEATING_TEMP：降低加熱爐設定溫度，並確認熱電偶校正與爐溫均勻度。 | Argmax Attribution & Rule-based Recommendation | Python Built-in |
| 5 | 歸因可信度 Guardrail 檢核 | 防呆檢核狀態：PASSED_WITH_WARNINGS。「加熱溫度」占比僅 44%，並非壓倒性主因，「冷卻水流量」（41%）也需一併檢查 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_16_root_cause_attribution_report import build_root_cause_report
result = build_root_cause_report(batch_id='B-2026-10')
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 根因指向「加熱溫度」（歸因占比 44%，風險分數 0.92）。建議：降低加熱爐設定溫度，並確認熱電偶校正與爐溫均勻度。

完整結果 JSON：`results/skill_16_root_cause_attribution_report_result.json`（2026-11-16 執行）。
