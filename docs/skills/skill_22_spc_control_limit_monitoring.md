# SKILL: skill_22_spc_control_limit_monitoring

**name**: `skill_22_spc_control_limit_monitoring`  
**description**: SPC 管制監控：以 Mean ± 3σ 算出管制上下限，找出超界點，並檢查連續 8 點同側等輔助判異規則。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-13 |
| 網頁 | 12 製程分群與 SPC |
| 演算法 | SPC（Mean ± 3σ） |
| 講義週次 | —（延伸，課堂未教） |
| 呼叫順序 | 12 頁：skill_21 → skill_20 → skill_22 |
| 程式檔 | `skills/skill_22_spc_control_limit_monitoring.py` |
| 主函式 | `monitor_spc()` |
| MCP 工具名 | `skill_22_spc_control_limit_monitoring` |

---

## 1. 做什麼

**使用者**：品質與製程工程師

以基準期資料計算平均與樣本標準差，UCL = μ + 3σ、LCL = μ − 3σ，超出者為異常點。另提供個別值移動全距（I-MR）的穩健 σ = MR̄ / 1.128 對照；輔助規則包括連續 8 點落在中心線同側（疑似位移）與 lag-1 自相關 > 0.5，只警告、不計入異常點數。

**程式內的演算法流程**：序列防呆 -> 基準期平均與標準差 -> UCL/LCL = μ ± 3σ -> 超界點與輔助判異規則 -> Guardrail

---

## 2. 輸入

函式：`monitor_spc(data_series=None, baseline_n=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `data_series` | Array[Float] | 是 | — | 要監控的數值序列（12 頁預設為溫度 z 分數） |
| `baseline_n` | Integer | 否 | `None` | 前 N 點作為基準期；未指定時用全部資料計算界限 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "data_series": "<300 筆資料>",
  "baseline_n": null
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `spc_limits` | Object | 管制界限：UCL、LCL、中心線與 σ | `{"ucl": 3.0, "lcl": -3.0, "center": 0.0, "sigma": 1.0}` |
| `outliers_count` | Integer | 超出管制界限的點數 | `1` |
| `outlier_indices` | Array | 超界點的位置 | `[201]` |
| `outliers` | Array | 超界點的位置、數值與方向 | `[{"index": 201, "value": -3.1327, "side": "below"}]` |
| `robust` | Object | I-MR 穩健 σ 與對應的管制界限（對照用） | `{"sigma_imr": 0.9888, "ucl": 2.9664, "lcl": -2.9664, "outliers_count":…}` |
| `run_violations` | Array | 連續 8 點以上落在中心線同側的區段 | `[{"start": 69, "end": 76, "length": 8, "side": "below"}, …]`（共 3 筆） |
| `lag1_autocorrelation` | Float | lag-1 自相關（> 0.5 代表獨立性假設可能不成立） | `0.0172` |
| `n_points` | Integer | 序列長度 | `300` |
| `baseline_n` | null | 基準期點數（未指定為 null） | `null` |
| `basis` | String | 界限計算依據：`all_points`（全部資料）或基準期 | `all_points` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["輸入本身就是以同一份資料算出的 z 分數（平均 0、標準差 1），限界必然是 ±3，等於只在檢查 \|z\|>3，不是獨立…, …]`（共 2 筆） |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `UCL=3.000、LCL=-3.000，300 點中有 1 點超出管制界限（建議留意位移）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 輸入若是用同一份資料算出的 z 分數，界限必然是 ±3，管制圖只是在檢查 |z| > 3，不是獨立的管制標準；應以 `baseline_n` 指定基準期。報告中列為已知限制。
2. 用全部資料算 σ 時，異常點本身會把 σ 撐大、界限變寬。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| 專案內模組 | — | 本專案 | `_common` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

課堂未教，以 20 點小例子依定義手算驗證（附件 A-4）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| UCL（20 點小例子手算） | 3.6054 | 3.605431 | 一致 | 課堂沒有教 SPC，用定義手算 |
| LCL（20 點小例子手算） | -2.9634 | -2.9634 | 一致 | 31 |
| 超界點數 | 1 | 1 | 一致 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 數據序列與基準期防呆 | 序列共 300 個有限數值（按時間順序）；以全部 300 點同時計算界限並檢查（規格預設做法）。 | Boundary & Type Validation | math |
| 2 | 計算基準期平均與標準差 | 基準期 300 點：平均 μ = 0.0000、樣本標準差 σ = 1.0000（分母 n-1）。 | Sample Mean & Standard Deviation (n-1) | statistics |
| 3 | 計算管制界限 UCL / LCL | UCL = μ + 3σ = 0.0000 + 3×1.0000 = 3.0000；LCL = μ - 3σ = -3.0000；中心線 CL = μ = 0.0000。 | Shewhart Control Limits  μ ± 3σ | Python Built-in |
| 4 | 標出超界點與輔助判異規則 | 超出 [-3.000, 3.000] 的點共 1 個（位置 201）。輔助檢查：連續 8 點同側的區段 3 處；lag-1 自相關 0.02；以相鄰點差估計的穩健 σ(I-MR) = MR̄/1.128 = 0.9888（對照樣本 σ=1.0000），以它算出的限界會抓到 1 點。 | Out-of-control Detection & Run Rule & I-MR σ Cross-check | Python Built-in |
| 5 | 管制圖可信度 Guardrail 檢核 | 防呆檢核狀態：PASSED_WITH_WARNINGS（≥20 點、σ>0）。輸入本身就是以同一份資料算出的 z 分數（平均 0、標準差 1），限界必然是 ±3，等於只在檢查 \|z\|>3，不是獨立於資料的管制標準；建議指定基準期 baseline_n；發現 3 段連續 8 點以上落在中心線同一側（最長 11 點），疑似製程平均位移，即使沒有點超界也需留意 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
# ... 代表網頁 API 傳入的大型資料（矩陣、前一個 Skill 的結果），由該頁 API 從模擬資料或前一步產生
from skill_22_spc_control_limit_monitoring import monitor_spc
result = monitor_spc(data_series=..., baseline_n=None)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> UCL=3.000、LCL=-3.000，300 點中有 1 點超出管制界限（建議留意位移）。

完整結果 JSON：`results/skill_22_spc_control_limit_monitoring_result.json`（2026-11-16 執行）。
