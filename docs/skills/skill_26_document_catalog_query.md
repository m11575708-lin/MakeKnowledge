# SKILL: skill_26_document_catalog_query

**name**: `skill_26_document_catalog_query`  
**description**: 文件目錄查詢：以 sqlite3 參數化查詢，依瀏覽身分、類別、日期、關鍵字列出知識庫收錄的文件與其來源、授權、更新日期。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 檢索 |
| 對應故事 | US-17 |
| 網頁 | 02 文件收錄 |
| 演算法 | SQLite 元資料過濾 |
| 講義週次 | —（標準函式庫 sqlite3） |
| 呼叫順序 | 02 頁：skill_26 |
| 程式檔 | `skills/skill_26_document_catalog_query.py` |
| 主函式 | `query_document_catalog()` |
| MCP 工具名 | `skill_26_document_catalog_query` |

---

## 1. 做什麼

**使用者**：一般民眾與各工程師（要引用規範前確認出處與授權）

合併 `docs/` 文件（依 `data/catalog_manifest.json` 標註類別、日期、授權、是否公開）與 skill_27 匯入索引，載入記憶體內的 sqlite3 表，以參數化 SQL 過濾（查詢條件不拼接進 SQL 字串），排序分頁後輸出。民眾身分只看得到公開文件，輸出前會再核對一次。

**程式內的演算法流程**：驗證身分與條件 -> 載入文件元資料 -> 參數化 SQL 過濾（角色、類別、日期、關鍵字）-> 排序分頁 -> 可見性核對

---

## 2. 輸入

函式：`query_document_catalog(role='public', categories=None, start_date=None, end_date=None, keyword=None, limit=50, offset=0, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `role` | String | 否 | `'public'` | 瀏覽身分：`public`（民眾，只看公開文件）或 `internal`、`engineer`、`admin`、`viewer`（內部，看全部）；不認得的角色一律拒絕 |
| `categories` | Array[String] | 否 | `None` | 類別篩選，例如 `["職安法規"]` |
| `start_date` | String | 否 | `None` | 更新日期起（`YYYY-MM-DD`） |
| `end_date` | String | 否 | `None` | 更新日期迄（`YYYY-MM-DD`） |
| `keyword` | String | 否 | `None` | 關鍵字（比對名稱、類別、預覽與正文前 20,000 字） |
| `limit` | Integer | 否 | `50` | 每頁筆數 |
| `offset` | Integer | 否 | `0` | 分頁起點 |
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
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `documents` | Array | 文件清單（doc_id、名稱、類別、更新日期、授權、預覽、連結、是否公開） | `[{"doc_id": "law_dme_rules_art001", "source_name": "危險性機械及設備安…, …]`（共 50 筆） |
| `total` | Integer | 符合條件的總筆數 | `234` |
| `returned` | Integer | 本頁筆數 | `50` |
| `categories_available` | Array | 各類別文件數 | `[{"category": "職安法規", "count": 234}]` |
| `filters` | Object | 實際套用的篩選條件 | `{"role_view": "public", "categories": null, "start_date": null, "end_d…}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `共 234 份文件符合條件，本頁顯示 50 份。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |
| `generated_at` | String | 結果產生時間（ISO 8601） | `2026-11-16T22:44:07` |

---

## 4. 限制

1. `docs/` 的文件預設不公開，必須在 manifest 寫 `is_public: true` 才會出現在民眾清單。
2. 沒登記在 manifest 的文件：類別依檔名推測、更新日取檔案修改日、授權標為「未標註」，都是保守預設。
3. 匯入文件只比對預覽（前 200 字），不全文掃描。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

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
| `pathlib` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| `secrets` | Python 標準函式庫 | PSF License 2.0 | 權杖 |
| `shutil` | Python 標準函式庫 | PSF License 2.0 | 檔案搬移 |
| `sqlite3` | Python 標準函式庫 | PSF License 2.0 | SQLite 文件索引 |
| `sys` | Python 標準函式庫 | PSF License 2.0 | 搜尋路徑 |
| `unicodedata` | Python 標準函式庫 | PSF License 2.0 | NFKC 正規化 |
| `zlib` | Python 標準函式庫 | PSF License 2.0 | — |
| 專案內模組 | — | 本專案 | `_catalog`, `_common`, `_doc_readers`, `_import_registry`, `_kb_store`, `skill_27_kb_import_pipeline` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

非演算法 Skill，以「民眾看不到內部文件」「日期與類別篩選」各 1 筆測試驗證。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 驗證身分與篩選條件 | 身分判定為「公開（一般民眾）」；條件：類別 不限、日期 不限 ～ 不限、關鍵字 無、每頁 50 筆、起點 0。 | Role & Input Validation Guardrail | re, datetime |
| 2 | 載入文件元資料 | 載入 234 份文件的元資料：docs/ 234 份、匯入索引 0 份；其中已宣告公開 234 份。 | Metadata Loading (docs/ + import index) | os, json, sqlite3 |
| 3 | 參數化 SQL 過濾 | 在可見的 234 份文件中以參數化 SQL（WHERE 0 個條件）過濾，符合 234 份。公開身分只會看到 is_public=1 的文件。 | Parameterised SQL Filtering (role, category, date, keyword) | sqlite3 |
| 4 | 排序與分頁 | 依 updated_at 由新到舊（同日以 doc_id）排序，取第 1–50 筆（共 234 筆）。 | ORDER BY updated_at DESC + LIMIT/OFFSET | sqlite3 |
| 5 | 可見性核對與輸出組裝 | 可見性核對通過（每一列 is_public=1）。防呆檢核狀態：PASSED。 | Visibility Re-check Guardrail | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_26_document_catalog_query import query_document_catalog
result = query_document_catalog()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 共 234 份文件符合條件，本頁顯示 50 份。

完整結果 JSON：`results/skill_26_document_catalog_query_result.json`（2026-11-16 執行）。
