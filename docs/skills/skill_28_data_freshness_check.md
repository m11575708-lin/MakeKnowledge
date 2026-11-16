# SKILL: skill_28_data_freshness_check

**name**: `skill_28_data_freshness_check`  
**description**: 資料新鮮度檢查：讀出各資料集的最新日期，依基準日算落後月數與時間衰減權重 e^(−λΔt)，落後超過門檻就提醒。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 維運與評估 |
| 對應故事 | US-19 |
| 網頁 | 04 維運評估 |
| 演算法 | 落後月數 + 時間指數衰減 |
| 講義週次 | —（標準函式庫 datetime、statistics） |
| 呼叫順序 | 04 頁：skill_28（與 skill_29 並列） |
| 程式檔 | `skills/skill_28_data_freshness_check.py` |
| 主函式 | `check_data_freshness()` |
| MCP 工具名 | `skill_28_data_freshness_check` |

---

## 1. 做什麼

**使用者**：管理者（決定要不要重新匯入資料）

每個資料集標出日期依據：`data`（資料內真的有日期，最可靠）、`file_mtime`（只能用檔案修改時間）、`import_time`（只知道匯入時間）、`none`（無法判斷，不計入）。落後月數 Δt 以年×12+月相減，權重 W = e^(−λΔt)；落後超過門檻（預設 3 個月）才提醒，新鮮度指數為有日期資料集權重的平均。

**程式內的演算法流程**：蒐集各資料集最新日期 -> 落後月數 -> 時間衰減權重 W(t) = e^(-λ·Δt) -> 門檻比對

---

## 2. 輸入

函式：`check_data_freshness(today=None, max_lag_months=3, decay_lambda=0.1, system_version=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `today` | String | 否 | `None` | 基準日（`YYYY-MM-DD`）；未提供時用今天 |
| `max_lag_months` | Integer | 否 | `3` | 落後門檻（月），超過才提醒 |
| `decay_lambda` | Float | 否 | `0.1` | 衰減係數 λ |
| `system_version` | String | 否 | `None` | 系統版本標記（只用於輸出） |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "today": "2026-11-16"
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `datasets` | Array | 各資料集的來源、最新日期、日期依據、落後月數、權重與提醒 | `[{"name": "分析資料・感測器歷史資料（壽命預測）", "kind": "analysis_csv", "data…, …]`（共 10 筆） |
| `data_freshness_status` | String | 整體狀態（正常／需更新） | `正常` |
| `expiration_warning` | Array | 落後超過門檻的資料集 | `[]` |
| `stale_count` | Integer | 需更新的資料集數 | `0` |
| `unknown_count` | Integer | 無法判斷的資料集數 | `9` |
| `known_count` | Integer | 有日期的資料集數 | `1` |
| `freshness_index` | Float | 新鮮度指數（0–1，僅供參考） | `1.0` |
| `params` | Object | 實際套用的參數 | `{"today": "2026-11-16", "max_lag_months": 3, "decay_lambda": 0.1}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["9 個資料集無法判斷新舊（沒有檔案或沒有日期），未計入「需更新」", …]`（共 2 筆） |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `基準日 2026-11-16：正常。0 個資料集落後超過 3 個月，9 個無法判斷，新鮮度指數 1.0。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |
| `generated_at` | String | 結果產生時間（ISO 8601） | `2026-11-16T22:44:07` |
| `system_version` | null | 系統版本標記 | `null` |

---

## 4. 限制

1. 只檢查資料有多舊，無法判斷內容是否仍符合現行法規；法規是否修訂需人工對照官方公告。
2. 目前 9 個分析資料集都是模擬資料、沒有日期，結果為「無法判斷」；法規文件以檔案修改日計算，不是法規修正日。
3. 最新日期晚於基準日視為資料異常，落後記為 0 並加警語。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `contextlib` | Python 標準函式庫 | PSF License 2.0 | 資源管理 |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `datetime` | Python 標準函式庫 | PSF License 2.0 | 日期處理 |
| `importlib` | Python 標準函式庫 | PSF License 2.0 | — |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `pathlib` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| `shutil` | Python 標準函式庫 | PSF License 2.0 | 檔案搬移 |
| `sqlite3` | Python 標準函式庫 | PSF License 2.0 | SQLite 文件索引 |
| `statistics` | Python 標準函式庫 | PSF License 2.0 | 平均數、標準差 |
| `sys` | Python 標準函式庫 | PSF License 2.0 | 搜尋路徑 |
| 專案內模組 | — | 本專案 | `_common`, `_import_registry`, `_kb_store` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

規格範例：最新 2026-06、基準日 2026-11-11 → 落後 5 個月，權重 e^(−0.1×5) = 0.6065，與程式一致。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 驗證基準日與參數 | 基準日 2026-11-16、落後門檻 3 個月、衰減係數 λ=0.1，皆通過檢查。 | Input Validation Guardrail | datetime, re |
| 2 | 蒐集各資料集最新日期 | 掃描 10 個資料集：資料內日期 0 個、檔案修改時間 1 個、匯入時間 0 個、無法判斷 9 個。 | Dataset Latest-date Scan | sqlite3, csv, os |
| 3 | 計算落後月數 Δt | 落後月數 Δt = (基準日年×12+月) − (最新日期年×12+月)，日期含「日」且基準日還沒到該日時再減 1；檢索文件・法規與標準（docs/） 落後 0 個月 | Calendar-month Lag | datetime |
| 4 | 計算時間衰減權重 W(t) | 權重 W(t) = e^(−λ·Δt)，λ=0.1（半衰期約 6.9 個月）；有日期資料集的平均權重（新鮮度指數）為 1.0。 | Exponential Time Decay W(t)=e^(-λΔt) | math, statistics |
| 5 | 門檻比對與新鮮度判定 | 落後超過 3 個月者標為需更新：0 個資料集超過門檻、9 個無法判斷。整體判定：正常。防呆檢核狀態：PASSED_WITH_WARNINGS。 | Threshold-based Freshness Guardrail | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_28_data_freshness_check import check_data_freshness
result = check_data_freshness(today='2026-11-16')
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 基準日 2026-11-16：正常。0 個資料集落後超過 3 個月，9 個無法判斷，新鮮度指數 1.0。

完整結果 JSON：`results/skill_28_data_freshness_check_result.json`（2026-11-16 執行）。
