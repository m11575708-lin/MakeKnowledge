# SKILL: skill_12_repair_log_entry_validation

**name**: `skill_12_repair_log_entry_validation`  
**description**: 維修紀錄欄位驗證：以正則表達式與臨界值檢查設備 ID、日期、故障碼、處置說明、電流與壓力，一次列出所有錯誤欄位。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 整理 |
| 對應故事 | US-08 |
| 網頁 | 09 維修登錄驗證 |
| 演算法 | 正則表達式 + 臨界值檢查 |
| 講義週次 | —（標準函式庫 re） |
| 呼叫順序 | 09 頁：skill_12 → skill_13 |
| 程式檔 | `skills/skill_12_repair_log_entry_validation.py` |
| 主函式 | `validate_repair_log_entry()` |
| MCP 工具名 | `skill_12_repair_log_entry_validation` |

---

## 1. 做什麼

**使用者**：設備維修工程師（修完登錄紀錄）

依序做欄位存在與型別檢查、正則格式驗證（設備 ID、ISO 日期時間、故障碼、處置說明至少 10 字）、硬上下限檢查（物理上不可能的數值直接判錯），以及常態範圍檢查（超出只警告）。與其他 Skill 不同，本 Skill 不中途停止，會把所有錯誤一次列出，方便一次改完；驗證通過後輸出正規化的紀錄交給 skill_13。

**程式內的演算法流程**：欄位存在與型別檢查 -> 正則表達式格式驗證 -> 臨界值（硬上下限）邊界檢查 -> 跨欄位邏輯與常態範圍檢查 -> 彙整判定與正規化輸出

---

## 2. 輸入

函式：`validate_repair_log_entry(current_a=None, pressure_mpa=None, equipment_id=None, repair_datetime=None, error_code=None, description=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `current_a` | Float | 是 | — | 電流（A） |
| `pressure_mpa` | Float | 是 | — | 壓力（MPa） |
| `equipment_id` | String | 否 | `None` | 設備 ID，格式 `EQ-英文 2–10 字-2～3 位數字`，例如 `EQ-PRESS-01` |
| `repair_datetime` | String | 否 | `None` | 維修日期時間（ISO 格式，例如 `2026-11-16T10:30`） |
| `error_code` | String | 否 | `None` | 故障碼，格式 `E-` 加 4 位數字，例如 `E-8021` |
| `description` | String | 否 | `None` | 處置說明（10–500 字，不能只有數字或符號） |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "current_a": 45.2,
  "pressure_mpa": 2.1,
  "equipment_id": "EQ-PRESS-01",
  "repair_datetime": "2026-11-16T10:30",
  "error_code": "E-8021",
  "description": "更換馬達軸承並清潔冷卻風扇濾網"
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `is_valid` | Boolean | 是否全部通過 | `true` |
| `message` | String | 驗證結論 | `FIELD_VALIDATION_PASSED` |
| `input_echo` | Object | 原始輸入 | `{"current_a": 45.2, "pressure_mpa": 2.1}` |
| `field_results` | Array | 逐欄位的檢查結果（欄位、是否通過、訊息） | `[{"field": "equipment_id", "label": "設備 ID", "ok": true, "mes…, …]`（共 6 筆） |
| `error_count` | Integer | 錯誤欄位數 | `0` |
| `normalized_entry` | Object | 正規化後的紀錄（交給 skill_13） | `{"equipment_id": "EQ-PRESS-01", "error_code": "E-8021", "repair_dateti…}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `所有欄位通過驗證。` |
| `limits` | Object | 硬上下限與常態範圍設定 | `{"hard": {"current_a": [0.0, 500.0], "pressure_mpa": [0.0, 30.0]}, "so…}` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸出 `invalid_fields`，程式改用 `field_results` 與 `error_count`。


---

## 4. 限制

1. 只有電流與壓力必填；其他欄位有提供才檢查。
2. 常態範圍（電流 5–80 A、壓力 0.5–3.2 MPa）是示範值，應依設備銘牌調整。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `datetime` | Python 標準函式庫 | PSF License 2.0 | 日期處理 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| 專案內模組 | — | 本專案 | `_common`, `_repair_data` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

規則檢查，以「格式錯誤、超出硬上限、超出常態範圍」各 1 筆測試即可驗證（09 頁快速測試已涵蓋）。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 欄位存在與型別檢查 | 必填數值欄位 2 項（電流、壓力），選填文字欄位提供 4 項；型別與存在檢查發現 0 項問題。 | Presence & Type Validation | math |
| 2 | 正則表達式格式驗證 | 以正則與解析驗證設備 ID（^EQ-[A-Z]{2,10}-\d{2,3}$）、故障碼（^E-\d{4}$）、ISO 日期時間與處置說明文字，共檢查 4 項，0 項不合格。 | Regular Expression Format Validation | re, datetime |
| 3 | 臨界值硬上下限邊界檢查 | 硬上下限：即時電流 [0, 500] A；即時壓力 [0, 30] MPa。超出者共 0 項。 | Boundary Value Check (Hard Limits) | math |
| 4 | 跨欄位邏輯與常態範圍檢查 | 常態範圍（警告用，不擋儲存）：電流 [5, 80] A、壓力 [0.5, 3.2] MPa；超出 0 項；跨欄位檢查（電流≈0 卻有壓力）產生 0 則警告。 | Cross-field Consistency & Soft-limit Check | Python Control Flow |
| 5 | 驗證結果彙整與正規化輸出 | 防呆檢核狀態：PASSED。共 6 項欄位檢查，通過 6、失敗 0；警告 0 則。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_12_repair_log_entry_validation import validate_repair_log_entry
result = validate_repair_log_entry(current_a=45.2, pressure_mpa=2.1, equipment_id='EQ-PRESS-01', repair_datetime='2026-11-16T10:30', error_code='E-8021', description='更換馬達軸承並清潔冷卻風扇濾網')
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 所有欄位通過驗證。

完整結果 JSON：`results/skill_12_repair_log_entry_validation_result.json`（2026-11-16 執行）。
