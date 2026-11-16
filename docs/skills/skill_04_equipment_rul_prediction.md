# SKILL: skill_04_equipment_rul_prediction

**name**: `skill_04_equipment_rul_prediction`  
**description**: 設備剩餘壽命（RUL）預測：以多元線性迴歸（OLS 閉式解）從 4 項感測值預測還能運轉幾小時，附 95% 區間與健康度燈號。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-03 |
| 網頁 | 06 設備壽命預測 |
| 演算法 | 多元線性迴歸（OLS） |
| 講義週次 | 第 5 週 |
| 呼叫順序 | 06 頁：skill_03 → skill_04 → skill_05 |
| 程式檔 | `skills/skill_04_equipment_rul_prediction.py` |
| 主函式 | `predict_equipment_rul()` |
| MCP 工具名 | `skill_04_equipment_rul_prediction` |

---

## 1. 做什麼

**使用者**：設備維修工程師

排保養時，工程師輸入累積運轉時數、振動值、溫度、負載率，Skill 先 Z-Score 標準化，再以 β = (XᵀX)⁻¹Xᵀy（手寫高斯消去法）擬合 OLS 模型，預測剩餘壽命（小時），並以固定 80/20 切分在測試集報告 MAE、RMSE、R²。同時給出 95% 預測區間、健康度百分比與紅黃綠燈號，以及隨運轉時數變化的衰退曲線。

**程式內的演算法流程**：輸入防呆 -> Z-Score -> OLS 閉式解 β=(XᵀX)⁻¹Xᵀy（手寫高斯消去法） -> 預測與 holdout 評估 (MAE / RMSE / R²) -> 外插與模型品質 Guardrail

---

## 2. 輸入

函式：`predict_equipment_rul(operating_hours=1500, vibration=2.8, temperature=75, load_rate=85, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `operating_hours` | Float | 否 | `1500` | 累積運轉時數（小時） |
| `vibration` | Float | 否 | `2.8` | 振動值（mm/s） |
| `temperature` | Float | 否 | `75` | 運轉溫度（°C） |
| `load_rate` | Float | 否 | `85` | 負載率（%） |
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
| `inputs` | Object | 實際採用的輸入值（經型別轉換後） | `{"operating_hours": 1500.0, "vibration": 2.8, "temperature": 75.0, "lo…}` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=42)` |
| `eval_metrics` | Object | 測試集評估指標與訓練／測試筆數（測試集不參與訓練） | `{"mae": 7.995, "rmse": 9.497, "r2": 0.9954, "n_train": 160, "n_test": …}` |
| `intercept` | Float | 截距（原始單位） | `1010.3616` |
| `regression_coefficients` | Object | 原始單位的迴歸係數（每增加 1 單位對結果的影響） | `{"operating_hours": -0.19931, "vibration": -29.90105, "temperature": -…}` |
| `standardized_coefficients` | Object | Z-Score 標準化後的係數（可互相比較大小） | `{"operating_hours": -135.7388, "vibration": -36.9135, "temperature": -…}` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `predicted_rul_hours` | Float | 預測剩餘壽命（小時，下限截斷為 0） | `322.55` |
| `prediction_interval` | Array | 95% 預測區間 [下限, 上限] | `[303.93, 341.16]` |
| `health_index_pct` | Float | 健康度百分比 | `49.79` |
| `health_level` | String | 燈號：`GREEN` / `YELLOW` / `RED` | `YELLOW` |
| `degradation_curve` | Array | 其他條件固定、運轉時數變化時的預測 RUL（畫衰退趨勢圖用） | `[{"operating_hours": 208.2, "predicted_rul_hours": 580.03}, …]`（共 12 筆） |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `預估剩餘使用壽命約 322.5 小時（約 13.4 天），95% 區間 304–341 小時，健康度 50%（YELLOW）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 沒有 `data/sensor_history.csv` 時用模擬資料（seed=42，訓練 160、測試 40），R² 0.995 是因為模擬資料本身是線性產生的，不代表真實設備能達到。
2. 線性模型假設各感測器對壽命的影響是直線且可相加；輸入超出訓練範圍時屬外插，會加警語。
3. 結果僅供參考，不可取代原廠保養週期與現場判斷（06 頁有標示）。
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
| 專案內模組 | — | 本專案 | `_common`, `skill_03_sensor_data_preprocessing` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `regress.py multi`（講義第 5 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| 截距（原始單位） | 1010.361594 | 1010.361594 | 一致 |  |
| 係數 operating_hours | -0.199314 | -0.199314 | 一致 |  |
| 係數 vibration | -29.901052 | -29.901052 | 一致 |  |
| 係數 temperature | -2.462241 | -2.462241 | 一致 |  |
| 係數 load_rate | -1.417055 | -1.417055 | 一致 |  |
| 測試 MAE | 7.994888 | 7.994888 | 一致 |  |
| 測試 RMSE | 9.497246 | 9.497246 | 一致 |  |
| 測試 R² | 0.995432 | 0.995432 | 一致 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入邊界與型別防呆 | 4 個感測器欄位皆為有限數值且位於物理合理範圍內。 | Boundary & Type Validation | math |
| 2 | Z-Score 標準化（以訓練集統計量） | 以訓練集 160 筆（資料來源：synthetic_demo (seed=42)）計算 μ、σ，並將本次輸入轉為 z 分數。 | Z-Score Standardization (StandardScaler) | statistics, skill_03 |
| 3 | 最小平方法閉式解求迴歸係數 | 組成設計矩陣 X（含截距欄），求解 (XᵀX)β = Xᵀy 得 β：operating_hours: -135.74；vibration: -36.91；temperature: -30.63；load_rate: -18.84；截距(標準化空間) 375.92。 | OLS Normal Equation (Gauss-Jordan Elimination) | Python Built-in (純 list 矩陣運算) |
| 4 | RUL 預測與測試集評估指標 | ŷ = β₀ + Σβᵢzᵢ = 322.5 h。測試集 40 筆：MAE=7.99、RMSE=9.50、R²=0.995。健康度 49.8%（<20% RED、<50% YELLOW、其餘 GREEN）。 | Multiple Linear Regression Prediction (MAE / RMSE / R²) | math |
| 5 | 外插與模型品質 Guardrail 檢核 | 防呆檢核狀態：PASSED（R²=0.995 ≥ 0.5）。輸入皆在訓練資料範圍內。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_04_equipment_rul_prediction import predict_equipment_rul
result = predict_equipment_rul()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 預估剩餘使用壽命約 322.5 小時（約 13.4 天），95% 區間 304–341 小時，健康度 50%（YELLOW）。

完整結果 JSON：`results/skill_04_equipment_rul_prediction_result.json`（2026-11-16 執行）。
