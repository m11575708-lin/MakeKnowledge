# SKILL: skill_01_tool_regulation_search

**name**: `skill_01_tool_regulation_search`  
**description**: 工具與公開法規檢索技能 (Tool & Regulation Search Skill)，用於查詢市售工具、危險性機械檢驗規定、CNS 國家標準與 SOP 保養指引。

---

## 1. 這個 Skill 做什麼 (What it does)

本 Skill 專為一般民眾、設備維修工程師及品質安衛人員設計。針對「市售工具與公開法規檢索」業務（對應系統規格 `US-01` 及選單頁 `01. 製造知識庫檢索與智慧問答頁`），接收使用者輸入的自然語言提問（如「衝壓機馬達過熱檢修規定」），透過 **TF-IDF 詞頻向量化** 與 **K 近鄰演算法 (KNN)** 的 **餘弦相似度 (Cosine Similarity)** 計算，從製造知識庫中精確檢索出 Top-K 最相關的 CNS 國家標準、BSMI 檢驗辦法與 SOP 指引。

同時實作 **Guardrail 得分防呆機制**：當最高相似度得分低於指定門檻時，自動觸發防呆保護並輸出固定提示（「查不到相關法規與案例資料」），確保 AI 解答嚴格基於可追溯之事實（Grounded Sources）。

---

## 2. 輸入欄位 (Inputs)

| 欄位名稱 | 型態 (Type) | 必填 | 預設值 | 說明 / 範例 |
| :--- | :--- | :--- | :--- | :--- |
| `query_text` | String | 是 | - | 使用者自然語言查詢字串（例如：「衝壓機馬達過熱檢修規定與 CNS 安全標準」） |
| `scope` | String | 否 | `"all"` | 檢索範疇：`all` (全區)、`regulations` (公開法規/CNS)、`repairs` (維修履歷) |
| `top_k` | Integer | 否 | `3` | 擷取最相似近鄰條文數量 $K$ |
| `threshold` | Float | 否 | `0.25` | Guardrail 得分防呆門檻（範圍 0.0 ~ 1.0） |
| `output_json_path` | String | 否 | `"/workspace/scratch/tool_regulation_search_result.json"` | 運算結果 JSON 檔案寫入路徑 |

---

## 3. 輸出欄位 (Outputs)

| 欄位名稱 | 型態 (Type) | 說明 / 範例 |
| :--- | :--- | :--- |
| `status` | String | 執行狀態（例如 `"success"`） |
| `found` | Boolean | 是否命中有效法規條文（`true` / `false`） |
| `query` | String | 原始查詢字串 |
| `scope` | String | 實際套用之檢索範疇 |
| `similarity_score` | Float | 最高匹配條文之餘弦相似度得分 (0.0000 ~ 1.0000) |
| `threshold` | Float | 套用之 Guardrail 得分門檻 |
| `answer_text` | String | 條理化解答卡片內文，或防呆提示文字 |
| `source_title` | String | 主要引用之法規/CNS標準名稱 |
| `source_url` | String | 引用來源檔案 PDF 或章節連結 |
| `search_results` | Array | Top-K 最相似法規條文清單（未命中時為空陣列） |
| `steps` | Array | 演算法推導過程日誌陣列（供前端「這個結果怎麼算的」面板顯示） |

---

## 4. 限制 (Constraints)

1. **零外部套件依賴與離線重現**：核心運算採用 Python 標準庫（`math`, `re`, `collections`, `json`），確保在完全離線環境下穩定重現。
2. **Guardrail 得分防呆**：當 `similarity_score < threshold` 時，`found` 必須設為 `false`，且 `answer_text` 必須輸出固定防呆提示：`"查不到相關法規與案例資料。系統無法從目前收錄之製造知識庫中獲取足夠數據以回答此問題，請重新調整檢索關鍵字。"`
3. **JSON 實體持久化與步驟日誌**：執行完畢後必須自動將運算成果寫入 `.json` 檔案，且 JSON 結構中必須包含 `steps` 陣列記錄計算與邏輯推導步驟。

---

## 5. 詳細步驟 (Steps)

1. **步驟 1：知識庫載入與範圍過濾 (Scope Filtering)**：載入製造知識庫數據，依 `scope` 欄位進行數據過濾。
2. **步驟 2：查詢字串分詞與向量化 (Tokenization)**：進行文本清洗、Unigram 與 Bigram 切分，提取特徵 Token。
3. **步驟 3：餘弦相似度計算 (Cosine Similarity Calculation)**：計算查詢向量與法規條文向量間之夾角餘弦值 $\cos(\theta) = \frac{\mathbf{A} \cdot \mathbf{B}}{\|\mathbf{A}\| \|\mathbf{B}\|}$。
4. **步驟 4：KNN Top-K 近鄰排序 (KNN Distance Ranking)**：依相似度降冪排序，採用 $K$ 近鄰邏輯擷取前 $K$ 個得分最高之條文。
5. **步驟 5：Guardrail 門檻比對與 JSON 輸出 (Guardrail Evaluation & JSON Export)**：比對最高分是否 $\ge threshold$，合成 Grounded 解答卡片與 `steps` 推導日誌，匯出標準 JSON 檔案。
