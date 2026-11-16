# SKILL: skill_05_degradation_feature_attribution

**name**: `skill_05_degradation_feature_attribution`  
**description**: 衰退特徵貢獻度拆解：重用 skill_04 的 OLS 模型，算出每個感測器讓這次預測的壽命比基準多或少幾小時，並排出影響最大的因素。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-03 |
| 網頁 | 06 設備壽命預測 |
| 演算法 | OLS 係數貢獻度拆解 |
| 講義週次 | 第 5 週 |
| 呼叫順序 | 06 頁：skill_03 → skill_04 → skill_05 |
| 程式檔 | `skills/skill_05_degradation_feature_attribution.py` |
| 主函式 | `attribute_degradation_features()` |
| MCP 工具名 | `skill_05_degradation_feature_attribution` |

---

## 1. 做什麼

**使用者**：設備維修工程師

回答「哪個感測器讓這台設備壽命變短」。基準 RUL（β₀）是所有特徵都等於訓練平均值時的預測；每個特徵的貢獻 cᵢ = βᵢ · zᵢ（小時），負值代表讓壽命縮短。依 |cᵢ| 佔比排序，找出主要驅動因素。

**程式內的演算法流程**：重用 skill_04 的 OLS 模型 -> 原始/標準化係數 -> 本次輸入的逐特徵貢獻 cᵢ = βᵢ·zᵢ（相對基準 RUL 的小時數）-> 佔比排序 -> Guardrail

---

## 2. 輸入

函式：`attribute_degradation_features(operating_hours=1500, vibration=2.8, temperature=75, load_rate=85, output_json_path=None)`

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
| `baseline_rul_hours` | Float | 基準 RUL：所有特徵等於訓練平均時的預測值 | `375.92` |
| `regression_coefficients` | Object | 原始單位的迴歸係數（每增加 1 單位對結果的影響） | `{"operating_hours": -0.19931, "vibration": -29.90105, "temperature": -…}` |
| `standardized_coefficients` | Object | Z-Score 標準化後的係數（可互相比較大小） | `{"operating_hours": -135.7388, "vibration": -36.9135, "temperature": -…}` |
| `contributions` | Array | 各特徵的 z 分數、係數、貢獻小時數、佔比與方向（延長／縮短壽命） | `[{"feature": "temperature", "label": "運轉溫度", "unit": "°C", "v…, …]`（共 4 筆） |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `top_driver` | String | 影響最大的特徵 | `temperature` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED (R² 0.995 >= 0.5)` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `本次工況下最主要的影響因子是「運轉溫度」，使 RUL 相對基準縮短 19.5 小時，佔總影響 37%。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸入有 `model_id`，程式不接受此參數，直接重用 skill_04 的模型。


---

## 4. 限制

1. 貢獻度描述的是「模型怎麼算」，不是物理因果；特徵之間高度相關時，個別係數會不穩定。
2. 與 skill_04 共用同一模型與資料來源，限制相同（模擬資料、外插）。
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
| 專案內模組 | — | 本專案 | `_common`, `skill_03_sensor_data_preprocessing`, `skill_04_equipment_rul_prediction` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

與 skill_04 共用 OLS 係數，對照結果見 skill_04。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

本 Skill 沒有獨立的比對列，說明見上。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入防呆並載入 OLS 模型 | 輸入通過驗證；重用 skill_04 的 OLS 模型（資料來源：synthetic_demo (seed=42)，訓練 160 筆）。 | Boundary Validation & Model Reuse | skill_03, skill_04 |
| 2 | 迴歸係數拆解（原始單位 / 標準化） | 原始單位係數 b = β_z / σ（每增加 1 單位對 RUL 的影響）：operating_hours: -0.199/h；vibration: -29.901/mm/s；temperature: -2.462/°C；load_rate: -1.417/%。 | OLS Coefficient Decomposition | Python Built-in |
| 3 | 逐特徵貢獻度計算 | 基準 RUL（所有特徵＝平均）= 375.9 h；cᵢ = βᵢ·zᵢ：operating_hours: -15.9h；vibration: -0.7h；temperature: -19.5h；load_rate: -17.1h。 | Contribution Analysis cᵢ = βᵢ·zᵢ | math |
| 4 | 貢獻佔比排序與主因判定 | 依 \|cᵢ\| 佔 Σ\|cⱼ\| 的百分比降冪排序：運轉溫度 36.6%；負載率 32.1%；累積運轉時數 29.9%；設備振動值 1.4%。 | Share-of-Impact Ranking | Python Built-in Sorting |
| 5 | Guardrail 檢核與歸因結論生成 | 防呆檢核狀態：PASSED (R² 0.995 >= 0.5)。主因：運轉溫度（縮短壽命，-19.5h）。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_05_degradation_feature_attribution import attribute_degradation_features
result = attribute_degradation_features()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED (R² 0.995 >= 0.5)`）：

> 本次工況下最主要的影響因子是「運轉溫度」，使 RUL 相對基準縮短 19.5 小時，佔總影響 37%。

完整結果 JSON：`results/skill_05_degradation_feature_attribution_result.json`（2026-11-16 執行）。
