# SKILL: skill_03_sensor_data_preprocessing

**name**: `skill_03_sensor_data_preprocessing`  
**description**: 感測器數據 Z-Score 標準化：用參考資料的平均與標準差，把運轉時數、振動、溫度、負載率轉成 z 分數，並檢查是否超出訓練資料範圍。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 整理 |
| 對應故事 | US-03、US-18 |
| 網頁 | 06 設備壽命預測（03 匯入感測器 CSV 時也會呼叫） |
| 演算法 | Z-Score 標準化 |
| 講義週次 | —（標準函式庫） |
| 呼叫順序 | 06 頁：skill_03 → skill_04 → skill_05；03 頁：skill_27 →（感測器 CSV）skill_03 |
| 程式檔 | `skills/skill_03_sensor_data_preprocessing.py` |
| 主函式 | `preprocess_sensor_data()` |
| MCP 工具名 | `skill_03_sensor_data_preprocessing` |

---

## 1. 做什麼

**使用者**：設備維修工程師（間接使用：由 06 頁與匯入流程呼叫）

載入參考資料（有 `data/sensor_history.csv` 就用真實資料，否則用固定 seed 的模擬資料），計算 4 個感測器欄位的平均數與樣本標準差，把本次輸入轉成 z = (x − μ) / σ。|z| 過大代表超出訓練資料範圍，後續迴歸屬於外插，會加警語。

**程式內的演算法流程**：參考資料載入 -> 輸入邊界防呆 -> 平均數/標準差 -> Z-Score 轉換 -> 外插 Guardrail

---

## 2. 輸入

函式：`preprocess_sensor_data(raw_values=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `raw_values` | Object | 是 | — | `{operating_hours, vibration, temperature, load_rate}` 四個數值；缺欄位或非數值會被擋下 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "raw_values": {
    "operating_hours": 1500,
    "vibration": 2.8,
    "temperature": 75,
    "load_rate": 85
  }
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=42)` |
| `n_samples` | Integer | 參考資料筆數 | `200` |
| `feature_order` | Array | 特徵順序 | `["operating_hours", "vibration", "temperature", "load_rate"]` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `raw_values` | Object | 原始輸入值 | `{"operating_hours": 1500.0, "vibration": 2.8, "temperature": 75.0, "lo…}` |
| `standardized_values` | Array | 依 feature_order 排列的 z 分數陣列 | `[0.1374, 0.0306, 0.612, 0.8879]` |
| `standardized` | Object | 各欄位的 z 分數（物件形式） | `{"operating_hours": 0.1374, "vibration": 0.0306, "temperature": 0.612,…}` |
| `reference_stats` | Object | 各欄位的平均、標準差、最小值、最大值 | `{"operating_hours": {"mean": 1405.5252, "std": 687.5041, "min": 208.15…}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `已完成 Z-Score 標準化：累積運轉時數 z=+0.14，設備振動值 z=+0.03，運轉溫度 z=+0.61，負載率 z=+0.89。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 沒有 `data/sensor_history.csv` 時用模擬資料（seed=42，200 筆），z 分數只代表相對於模擬資料的位置。
2. 超出物理合理範圍的輸入（例如負的運轉時數）直接擋下；在合理範圍但超出訓練資料範圍時只給外插警告。
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
| 專案內模組 | — | 本專案 | `_common` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

以 1 筆輸入手算 (x − μ) / σ 即可驗證；標準化公式與講義相同（本 Skill 用樣本標準差 n−1）。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 載入參考資料集 | 載入 200 筆參考資料（來源：synthetic_demo (seed=42)）作為標準化基準。 | Dataset Loader | csv, random |
| 2 | 輸入邊界與型別防呆 | 4 個欄位皆為有限數值且位於物理合理範圍內。 | Boundary & Type Validation | math |
| 3 | 計算特徵平均數與標準差 | 以樣本標準差 (n-1) 計算各特徵統計量：operating_hours μ=1405.53, σ=687.50；vibration μ=2.76, σ=1.24；temperature μ=67.41, σ=12.40；load_rate μ=73.04, σ=13.47 | Sample Mean / Standard Deviation | statistics |
| 4 | Z-Score 標準化轉換 | 套用 z = (x - μ) / σ：operating_hours=+0.137；vibration=+0.031；temperature=+0.612；load_rate=+0.888 | Z-Score Standardization (StandardScaler) | Python Built-in |
| 5 | 外插 Guardrail 檢核與結果輸出 | 防呆檢核狀態：PASSED。所有數值皆在訓練範圍內。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_03_sensor_data_preprocessing import preprocess_sensor_data
result = preprocess_sensor_data(raw_values={'operating_hours': 1500, 'vibration': 2.8, 'temperature': 75, 'load_rate': 85})
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 已完成 Z-Score 標準化：累積運轉時數 z=+0.14，設備振動值 z=+0.03，運轉溫度 z=+0.61，負載率 z=+0.89。

完整結果 JSON：`results/skill_03_sensor_data_preprocessing_result.json`（2026-11-16 執行）。
