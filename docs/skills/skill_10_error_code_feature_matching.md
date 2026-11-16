# SKILL: skill_10_error_code_feature_matching

**name**: `skill_10_error_code_feature_matching`  
**description**: 故障碼特徵比對與權重校正：依故障碼找出歷史典型模式，算出目前特徵與該模式的吻合度，並給 skill_09 用的校正權重。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 整理 |
| 對應故事 | US-06 |
| 網頁 | 08 案例與備品 |
| 演算法 | 故障碼對照 + 特徵標準化加權（逆變異數權重、高斯核親和度） |
| 講義週次 | —（標準函式庫） |
| 呼叫順序 | 08 頁：skill_10 → skill_09 → skill_11 |
| 程式檔 | `skills/skill_10_error_code_feature_matching.py` |
| 主函式 | `match_error_code_pattern()` |
| MCP 工具名 | `skill_10_error_code_feature_matching` |

---

## 1. 做什麼

**使用者**：設備維修工程師

同一故障碼的歷史案例中，某特徵越集中越能代表這種故障：相對離散度 rᵢ = σ組內ᵢ / σ全庫ᵢ，權重 wᵢ ∝ 1/rᵢ²（正規化成平均 1）。吻合度 conf = exp(−½·mean(zᵢ²))，z 為目前特徵相對該故障碼中心的標準化距離；這是核函數親和度，不是機率。

**程式內的演算法流程**：故障碼格式防呆 -> 依故障碼分組歷史案例 -> 特徵中心與組內標準差 -> 逆變異數權重校正 -> 高斯核親和度（信心度）-> Guardrail

---

## 2. 輸入

函式：`match_error_code_pattern(error_code='E-8021', feature_vector=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `error_code` | String | 否 | `'E-8021'` | 故障碼，格式 `E-` 加 4 位數字，例如 `E-8021` |
| `feature_vector` | Array[Float] | 否 | `None` | `[振動, 溫度, 壓力]`；有提供才會計算吻合度 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "error_code": "E-8021",
  "feature_vector": [
    2.8,
    75.0,
    1.8
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
| `error_code` | String | 查詢的故障碼 | `E-8021` |
| `feature_vector` | Array | 輸入的特徵向量 | `[2.8, 75.0, 1.8]` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `demo_cases (示範資料，非真實工單)` |
| `matched_pattern` | String | 對應模式代碼（例 `MOTOR_OVERHEAT`） | `MOTOR_OVERHEAT` |
| `pattern_label` | String | 模式中文名稱 | `馬達過熱` |
| `confidence` | Float | 吻合度（核親和度，0–1） | `0.9017` |
| `n_cases` | Integer | 該故障碼的歷史案例數 | `4` |
| `centroid` | Array | 該故障碼的特徵中心 | `[2.975, 77.25, 1.75]` |
| `within_std` | Array | 組內標準差 | `[0.35, 4.7871, 0.1291]` |
| `feature_weights` | Array | 校正後權重（傳給 skill_09） | `[0.8812, 0.1652, 1.9536]` |
| `feature_weights_by_name` | Object | 校正後權重（依特徵名稱） | `{"vibration": 0.8812, "temperature": 0.1652, "pressure": 1.9536}` |
| `z_scores` | Array | 目前特徵相對中心的 z 分數 | `[-0.5, -0.47, 0.3873]` |
| `known_error_codes` | Array | 案例庫中已知的故障碼 | `["E-6040", "E-7015", "E-8021", "E-8032"]` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `故障碼 E-8021 對應模式為 MOTOR_OVERHEAT（馬達過熱），共 4 筆歷史案例。目前特徵與該模式的吻合度（核親和度）為 0.…` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸入 `raw_features`，程式實際用 `feature_vector`。


---

## 4. 限制

1. 案例數少時組內標準差不穩，組內 σ 設下限為全庫 σ 的 10% 避免權重爆衝。
2. 不認得的故障碼會回查不到，不會猜測對應模式。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| 專案內模組 | — | 本專案 | `_common`, `_repair_data` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

權重與親和度為本專案設計的公式，【待補：以 1 個故障碼手算 r、w 與 conf】。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 故障碼格式與特徵向量防呆 | 故障碼 E-8021 格式正確；特徵向量 3 維皆為合理範圍內的有限數值。 | Regular Expression & Boundary Validation | re, math |
| 2 | 依故障碼分組歷史案例 | 自 demo_cases (示範資料，非真實工單) 載入 16 筆案例；故障碼 E-8021 共 4 筆（案例庫共 4 種故障碼）。 | Metadata Filtering (GroupBy error_code) | json, os |
| 3 | 特徵中心與組內標準差 | 組內特徵中心：振動值 2.98mm/s；運轉溫度 77.25°C；運轉壓力 1.75MPa；組內標準差（含下限）：0.350；4.787；0.129。 | Centroid & Sample Standard Deviation | Python Built-in |
| 4 | 逆變異數權重校正 | 先把組內標準差除以全案例庫標準差（去除單位，避免 °C 與 MPa 的量級影響），得相對離散度：振動值 0.304；運轉溫度 0.703；運轉壓力 0.204。再取 w ∝ 1/相對離散度² 並正規化為平均 1：振動值 0.881；運轉溫度 0.165；運轉壓力 1.954。權重越高代表該特徵越能區辨此故障碼。 | Inverse-Variance Feature Weighting  w ∝ 1/σ² | math |
| 5 | 高斯核信心度與 Guardrail 檢核 | 防呆檢核狀態：PASSED。信心度 conf = exp(-½·mean(z²)) = 0.902。 | Gaussian Kernel Affinity & Threshold-based Guardrail | math, Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_10_error_code_feature_matching import match_error_code_pattern
result = match_error_code_pattern(error_code='E-8021', feature_vector=[2.8, 75.0, 1.8])
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 故障碼 E-8021 對應模式為 MOTOR_OVERHEAT（馬達過熱），共 4 筆歷史案例。目前特徵與該模式的吻合度（核親和度）為 0.90。

完整結果 JSON：`results/skill_10_error_code_feature_matching_result.json`（2026-11-16 執行）。
