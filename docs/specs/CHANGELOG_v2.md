# 規格書 v2 修訂紀錄（2026-11-11）

## 一、 檔案異動

| 檔案 | 異動 |
| :--- | :--- |
| `KnowledgeStep01.md` | 新增「13 頁選單總表」為全專案標準；角色加入管理者；業務地圖改為 29 個 Skill |
| `KnowledgeStep02.md` | 故事 US-01–15 保留，新增 US-16–19；選單、Use Case（UC01–UC13）、線框全部改用 13 頁編號；角色表加入管理者 |
| `KnowledgeStep03.md` | SA 對照表與追溯表重寫；新增第二條業務流程（匯入）與驗證計畫 |
| `29_skill.md` | **取代 `25_skill.md`**（請把舊檔從專案刪除）；新增 Skill 26–29；skill_23 更名 |
| `9_code_artifact.md` | 每個演算法加「對答案工具」；延伸方法與平台機制分開列；新增套件授權規則 |

## 二、 主要統一決定

1. **頁數**：一律 13 頁。頁碼＝選單編號 M-xx＝Use Case UCxx。舊版 Step01 的 9 頁編號與 Step02 Use Case 的 01–09 編號全部廢止。
   * 舊 Use Case 編號對照：UC1→UC05、UC2→UC06、UC3→UC07、UC4→UC08、UC5→UC09、UC6→UC10、UC7→UC11、UC8→UC12、UC9→UC13；UC01–UC04 為新增。
2. **故事**：原 US-01–US-15 編號與內容不變（只修正驗收條件細節）；新增共同網頁故事：US-16（01 智慧問答）、US-17（02 文件收錄）、US-18（03 匯入）、US-19（04 維運）。
3. **管理者**：新增角色，負責 03、04 頁；工程師在 03 只能上傳檔案；廠長在 04 唯讀。
4. **Guardrail 門檻**：依現有程式統一為 skill_01 預設 0.10、skill_02 預設 0.20（舊規格的 0.50、0.60 廢止），標明是設計值、可在設定檔調整。
5. **套件**：Skill 只用標準函式庫；移除 scikit-learn、numpy。

## 三、 Skill 對應修正

| 問題（舊版） | 修正（v2） |
| :--- | :--- |
| 02 頁掛 skill_01、skill_12（欄位防呆和文件瀏覽無關） | 改為新增的 `skill_26_document_catalog_query` |
| 03 頁掛 skill_12、**skill_08 成本門檻**（與匯入無關） | 改為新增的 `skill_27_kb_import_pipeline` → `skill_03` |
| 04 頁掛 **skill_13 感知器**、skill_16 根因報告（與維運無關） | 改為新增的 `skill_28_data_freshness_check`、`skill_29_retrieval_quality_eval` |
| 01 頁掛 skill_09（數值特徵歐氏距離，不適合文字提問） | 01 頁只用 skill_01 + AnythingLLM |
| US-05 寫「成本取捨 + 時間指數衰減」 | 時間衰減移到 skill_28（US-19） |
| US-08 寫「感知器 + 正則清洗與雜湊去重」 | 雜湊去重移到 skill_27（US-18） |
| US-12 對到 03 匯入頁、US-13 寫「SPC + MRR」 | US-12、US-13 只對 12 頁；MRR 移到 skill_29 |
| skill_13 標 US-12 / US-08；skill_21 標 US-12 / US-13 | skill_13 → US-08；skill_21 → US-12 |
| `skill_23_production_index_hierarchical`（名稱是階層分群，內容是 MLP） | 更名 `skill_23_ipi_mlp_forecast` |
| 08 頁呼叫順序 09 → 10 → 11 | 改為 10（故障碼轉特徵）→ 09（KNN）→ 11（備品） |
| 12 頁呼叫順序 20 → 21 → 22 | 改為 21（先決定 K）→ 20 → 22 |
| Step02 選單把 Skill 範圍寫成 `skill_03~05` 出現在 07 頁、`skill_06~08` 出現在 08 頁等錯位 | 依實際呼叫鏈逐頁改正 |

## 四、 skill_23（類神經網路）是不是真的有訓練？

**判斷結果：目前沒有任何訓練。**專案裡沒有 skill_23 的程式（只有 skill_01、02 被 `app.py` 與 `mcp_server.py` 引用，而且這兩支 `.py` 也不在專案文件中）。規格裡的 `[108.5, 109.2, 110.1]`、`0.012` 都是設計時寫的示意值。

**v2 決定：要求真實訓練。**做法：用公開的月度工業生產指數資料，純 Python 實作單隱藏層 MLP，依時間切分訓練與測試，輸出逐輪 loss，並和「延續上月」的基準比較；結果不好也照實寫。

**之後怎麼自己分辨「真訓練」或「假的」：**

| 檢查 | 真訓練 | 假的 |
| :--- | :--- | :--- |
| 程式裡有沒有權重更新的迴圈（`for epoch …` 裡 `w -= lr * grad`） | 有 | 沒有，直接 `return` 固定數字 |
| 換一份資料、換隨機種子重跑 | 結果會變 | 結果永遠一樣 |
| `loss_history` | 逐輪大致下降 | 沒有，或只有一個數字 |
| 有沒有訓練／測試分開的誤差 | 有 | 沒有 |

## 五、 現有程式與規格不一致之處（本次**未改程式**，之後產出程式時一併修正）

1. **`app.py` 寫死 API 金鑰**：範本規定金鑰不能出現在檔案裡。請改成 `os.environ["ANYTHINGLLM_API_KEY"]`，並到 AnythingLLM 重新產生金鑰（舊金鑰已外流到專案文件）。
2. **`/api/search` 的 5 步 steps 與實際計算不符**：程式只呼叫 AnythingLLM，沒有呼叫 skill_01，但 steps 寫成 TF-IDF、餘弦、KNN；`similarity_score` 寫死 `0.95`。這和上面「假訓練」是同一類問題，需改為真的呼叫 skill_01 並回傳實際分數。
3. **`/api/documents` 用假資料（mock_documents）**：需改為呼叫 skill_26 查 SQLite。
4. **steps 寫的本機模型 qwen2.5:1.5b 屬中國來源**：範本規定非中國來源，建議改用 Phi-4-mini 等模型，並更新說明文字。
5. **steps 寫的套件 `numpy`**：與「只用標準函式庫」規則不符，需移除。
6. **page01 左側選單只列 01、02、05 三頁**：需改為完整 13 頁（檔名見 Step01 總表）。
7. **`mcp_server.py` 只有 skill_01、02 兩個工具**：其餘 Skill 完成後再陸續加入。
