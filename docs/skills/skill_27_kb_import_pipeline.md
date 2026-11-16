# SKILL: skill_27_kb_import_pipeline

**name**: `skill_27_kb_import_pipeline`  
**description**: 知識庫匯入管線：讀取已上傳的檔案，依序正則清洗、SHA-256 去重、筆數核對、滑動視窗切片並寫入 SQLite 索引，每步記錄失敗原因。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 匯入 |
| 對應故事 | US-18 |
| 網頁 | 03 匯入整理 |
| 演算法 | 正則清洗 + SHA-256 去重 + 滑動視窗切片 |
| 講義週次 | —（標準函式庫 re、hashlib） |
| 呼叫順序 | 03 頁：skill_27 →（感測器 CSV）skill_03 → 重跑模型類 Skill |
| 程式檔 | `skills/skill_27_kb_import_pipeline.py` |
| 主函式 | `import_kb_files()` |
| MCP 工具名 | `skill_27_kb_import_pipeline` |

---

## 1. 做什麼

**使用者**：管理者（執行匯入）；工程師可上傳

只讀 `data/uploads/` 裡已上傳的檔案。清洗移除控制字元與零寬字元、合併空白、把日期時間標準化成 ISO 格式；去重以 NFKC 正規化後的 SHA-256 判斷同檔內與跨次匯入的重複；筆數核對要求「讀進 = 保留 + 重複 + 空白 + 格式錯誤」且保留筆數 = 切片筆數，不符就不寫入；切片用固定長度滑動視窗（預設 500 字、重疊 50 字），在單一交易內寫入，寫入後再核對，不符就 rollback。

**程式內的演算法流程**：讀取與格式檢查 -> 正則清洗 -> SHA-256 雜湊去重 -> 筆數核對 -> 滑動視窗切片並寫入 SQLite 文件索引

---

## 2. 輸入

函式：`import_kb_files(files=None, rules=None, file_type=None, dry_run=False, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `files` | Array[String] | 是 | — | `data/uploads/` 中的檔名（只接受單純檔名） |
| `rules` | Object | 否 | `None` | `{strip_noise, normalize_datetime, dedupe, chunk_size, overlap}` |
| `file_type` | String | 是 | — | `維修履歷`、`感測器圖資`、`設備規格書`、`製程數據` 之一 |
| `dry_run` | Boolean | 否 | `False` | 試跑：完整檢查但不寫入索引與匯入紀錄（MCP 工具預設使用） |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "files": [
    "repair_import_demo.csv"
  ],
  "file_type": "維修履歷",
  "dry_run": true
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `import_progress_pct` | Integer | 整體進度（%） | `100` |
| `rows_read` | Integer | 讀進筆數 | `45` |
| `rows_cleaned_count` | Integer | 清洗後保留筆數 | `40` |
| `duplicate_rate_pct` | Float | 重複率（%） | `11.1` |
| `duplicates_removed` | Integer | 移除的重複筆數 | `5` |
| `chunks_created_count` | Integer | 產生的切片數 | `12` |
| `files` | Array | 逐檔結果（五步狀態、筆數、失敗原因） | `[{"file_name": "repair_import_demo.csv", "stored_name": "repa…, …]`（共 1 筆） |
| `failures` | Array | 失敗的檔案與原因 | `[]` |
| `rules` | Object | 實際套用的清洗與切片規則 | `{"strip_noise": true, "normalize_datetime": true, "dedupe": true, "chu…}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["這是預覽（dry_run）：沒有寫入索引或匯入紀錄"]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `1/1 個檔案匯入完成，保留 40 筆、重複率 11.1%、產生 12 個切片。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |
| `import_id` | String | 匯入批次編號 | `IMP-20261116224407-7708` |
| `dry_run` | Boolean | 是否為試跑 | `true` |

---

## 4. 限制

1. CSV 欄數不符的列視為格式錯誤並丟棄；超過 20% 整個檔案判失敗。無法解析的日期保持原樣並警告，不猜測。
2. 只有雜湊相同才算重複，內容相近但不同的段落不會合併。
3. 匯入的文件一律標為內部資料（is_public=0），不會出現在民眾清單。
4. 權限以環境變數權杖控制（`IMPORT_ADMIN_TOKEN` 等），沒有帳號系統；未設定時僅限本機開發。
5. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
6. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `contextlib` | Python 標準函式庫 | PSF License 2.0 | 資源管理 |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `datetime` | Python 標準函式庫 | PSF License 2.0 | 日期處理 |
| `hashlib` | Python 標準函式庫 | PSF License 2.0 | SHA-256 去重 |
| `importlib` | Python 標準函式庫 | PSF License 2.0 | — |
| `io` | Python 標準函式庫 | PSF License 2.0 | 文字串流 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| `secrets` | Python 標準函式庫 | PSF License 2.0 | 權杖 |
| `shutil` | Python 標準函式庫 | PSF License 2.0 | 檔案搬移 |
| `sqlite3` | Python 標準函式庫 | PSF License 2.0 | SQLite 文件索引 |
| `sys` | Python 標準函式庫 | PSF License 2.0 | 搜尋路徑 |
| `unicodedata` | Python 標準函式庫 | PSF License 2.0 | NFKC 正規化 |
| `zlib` | Python 標準函式庫 | PSF License 2.0 | — |
| 專案內模組 | — | 本專案 | `_common`, `_doc_readers`, `_import_registry`, `_kb_store` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

非演算法 Skill，以自製測試檔（45 列，其中 5 列重複）驗證：保留 40 列、重複率 11.1%。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 讀取檔案與格式檢查 | 收到 1 個檔案，1 個讀取成功：repair_import_demo.csv（CSV，資料列 45 筆）。 | File Read & Format Validation | csv, zlib, re |
| 2 | 正則清洗（非法字元、日期時間標準化） | 已套用：移除非法字元與合併空白、日期時間標準化。1 個檔案通過清洗；丟棄空白列／段落 0 筆、格式錯誤列 0 筆。 | Regular-expression Cleaning | re, unicodedata |
| 3 | SHA-256 雜湊去重 | 以 SHA-256（NFKC 正規化＋空白合併後）比對：檔內重複 5 筆、與索引內既有內容重複 0 筆，整體重複率 11.1%。 | SHA-256 Hash Deduplication | hashlib |
| 4 | 筆數核對 | 核對式：讀進筆數 = 保留 + 檔內重複 + 索引內重複 + 空白 + 格式錯誤；repair_import_demo.csv：45 = 40 + 5 + 0 + 0 + 0（通過）。 | Row Count Reconciliation | Python Built-in |
| 5 | 滑動視窗切片並寫入文件索引 | 預覽結果：1/1 個檔案完成，保留 40 筆、切片 12 個（未寫入）。防呆檢核狀態：PASSED_WITH_WARNINGS。 | Sliding-window Chunking + SQLite Index Write | sqlite3 |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_27_kb_import_pipeline import import_kb_files
result = import_kb_files(files=['repair_import_demo.csv'], file_type='維修履歷', dry_run=True)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 1/1 個檔案匯入完成，保留 40 筆、重複率 11.1%、產生 12 個切片。

完整結果 JSON：`results/skill_27_kb_import_pipeline_result.json`（2026-11-16 執行）。
