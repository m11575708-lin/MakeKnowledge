# SKILL: skill_06_failure_probability_calc

**name**: `skill_06_failure_probability_calc`  
**description**: 突發故障機率：用邏輯迴歸（IRLS 牛頓法）從距上次維修天數、近 90 天警報次數、壓力算出故障機率。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-04 |
| 網頁 | 07 故障風險評估 |
| 演算法 | 邏輯迴歸（Sigmoid） |
| 講義週次 | 第 5 週 |
| 呼叫順序 | 07 頁：skill_06 → skill_07 → skill_08 |
| 程式檔 | `skills/skill_06_failure_probability_calc.py` |
| 主函式 | `calculate_failure_probability()` |
| MCP 工具名 | `skill_06_failure_probability_calc` |

---

## 1. 做什麼

**使用者**：設備維修工程師（每日巡檢）

特徵先 Z-Score 標準化，以 IRLS 牛頓法擬合邏輯迴歸（含 L2 正則化 λ = 0.001），P(故障) = 1 / (1 + e^−(wᵀx + b))。以 80/20 切分在測試集報告 AUC、準確率與 Log-loss，並給出每個特徵的勝算比與 Sigmoid 曲線供網頁繪圖。

**程式內的演算法流程**：輸入防呆 -> 歷史資料載入與 80/20 切分 -> 邏輯迴歸 IRLS 牛頓法擬合 -> Sigmoid 機率轉換 -> 外插與模型品質 Guardrail

---

## 2. 輸入

函式：`calculate_failure_probability(recency_days=45, alarms_90d=12, pressure=1.8, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `recency_days` | Float | 否 | `45` | 距上次維修天數 |
| `alarms_90d` | Float | 否 | `12` | 近 90 天警報次數 |
| `pressure` | Float | 否 | `1.8` | 系統壓力（MPa） |
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
| `inputs` | Object | 實際採用的輸入值（經型別轉換後） | `{"recency_days": 45.0, "alarms_90d": 12.0, "pressure": 1.8}` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=42)` |
| `linear_score` | Float | 線性分數 z = wᵀx + b | `-0.8896` |
| `eval_metrics` | Object | 測試集評估指標與訓練／測試筆數（測試集不參與訓練） | `{"auc": 0.8944, "accuracy": 0.815, "log_loss": 0.3736, "n_train": 800,…}` |
| `intercept` | Float | 截距（原始單位） | `-7.33379` |
| `regression_coefficients` | Object | 原始單位的迴歸係數（每增加 1 單位對結果的影響） | `{"recency_days": 0.02234, "alarms_90d": 0.28507, "pressure": 1.12124}` |
| `standardized_coefficients` | Object | Z-Score 標準化後的係數（可互相比較大小） | `{"recency_days": 1.1613, "alarms_90d": 2.5026, "pressure": 0.7063}` |
| `feature_odds_ratios` | Array | 各特徵每增加 1 單位／1 個標準差的勝算比 | `[{"feature": "recency_days", "label": "距上次維修天數", "unit": "天",…, …]`（共 3 筆） |
| `sigmoid_curve` | Array | Sigmoid 曲線取樣點（畫圖用） | `[{"z": -7.0, "probability": 0.00091}, …]`（共 30 筆） |
| `converged` | Boolean | 牛頓法是否收斂 | `true` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `failure_probability` | Float | 故障機率（0–1） | `0.2912` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `在目前工況下，設備發生突發故障的機率約為 29.1%。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 沒有 `data/failure_history.csv` 時用模擬資料（seed=42，訓練 800、測試 200）。
2. 加了 L2 正則化 λ = 0.001（講義沒有），所以係數和講義公式算的差在小數第 4 位。
3. 機率是模型估計值，僅供維修排程參考（07 頁有標示）。
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
| `statistics` | Python 標準函式庫 | PSF License 2.0 | 平均數、標準差 |
| 專案內模組 | — | 本專案 | `_common`, `_failure_model`, `skill_03_sensor_data_preprocessing`, `skill_04_equipment_rul_prediction` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `logit.py train`（講義第 5 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| 截距（原始單位） | -7.333795 | -7.334069 | 一致 | Skill 加了 L2 正則化 λ＝0.001，講義沒有，係數會差一點 |
| 係數 recency_days | 0.022335 | 0.022336 | 一致 | Skill 加了 L2 正則化 λ＝0.001，講義沒有，係數會差一點 |
| 係數 alarms_90d | 0.28507 | 0.285082 | 一致 | Skill 加了 L2 正則化 λ＝0.001，講義沒有，係數會差一點 |
| 係數 pressure | 1.121242 | 1.121282 | 一致 | Skill 加了 L2 正則化 λ＝0.001，講義沒有，係數會差一點 |
| 測試準確率（門檻 0.5） | 0.815 | 0.815 | 一致 |  |
| 門檻 0.5 的混淆矩陣 TP/FP/FN/TN | — | 42/13/24/121 | 參考 | Skill 不輸出這一項，列出供參考 |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入邊界與型別防呆 | 3 個欄位皆為有限數值、位於物理合理範圍內，且警報次數為整數。 | Boundary & Type Validation | math |
| 2 | 載入歷史資料並切分訓練 / 測試集 | 自 synthetic_demo (seed=42) 載入資料，80/20 固定切分：訓練 800 筆（故障率 36.1%）、測試 200 筆（故障 66 / 正常 134）。 | Dataset Loader & 80/20 Holdout Split | csv, random |
| 3 | 邏輯迴歸係數擬合（牛頓法 IRLS） | IRLS 牛頓法 7 次迭代收斂；標準化係數 β：recency_days: +1.161；alarms_90d: +2.503；pressure: +0.706；截距 -0.759。 | Logistic Regression (Newton-Raphson / IRLS) | Python Built-in (純 list 矩陣運算) |
| 4 | Sigmoid 機率轉換 | 線性分數 z = wᵀx + b = -0.890；P(Y=1) = 1/(1+e^-z) = 0.2912。測試集 AUC=0.894、Accuracy=0.815、Log-loss=0.374。 | Sigmoid P(Y=1)=1/(1+e^-(wᵀx+b)) | math |
| 5 | 外插與模型品質 Guardrail 檢核 | 防呆檢核狀態：PASSED（AUC=0.894 ≥ 0.7、已收斂）。輸入皆在訓練資料範圍內。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_06_failure_probability_calc import calculate_failure_probability
result = calculate_failure_probability()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 在目前工況下，設備發生突發故障的機率約為 29.1%。

完整結果 JSON：`results/skill_06_failure_probability_calc_result.json`（2026-11-16 執行）。
