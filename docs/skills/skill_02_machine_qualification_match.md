# SKILL: skill_02_machine_qualification_match

**name**: skill_02_machine_qualification_match  
**description**: 機械設備與操作資格比對技能 (Machine Qualification Match Skill)，用於比對危險性機械（衝壓剪切機械、升降機具、電動工具等）之法定操作人員資格與安全檢驗規定。

---

## 1. 這個 Skill 做什麼 (Functional Overview)

本 Skill 專為一般民眾、廠區安衛管理人員及設備操作工程師設計，針對「危險性機械設備與操作資格比對」業務（對應系統規格 US-02 及選單頁「05. 公開法規與商品檢驗查詢頁面」）。

接收使用者輸入的機械設備類別（如「衝壓剪切機械」、「升降機具」）與既有操作證照/資格憑證，透過 **Jaccard 集合相似度 (Jaccard Similarity Coefficient)** 計算與 **K 近鄰演算法 (KNN)** 比對：
$$J(A, B) = \frac{|A \cap B|}{|A \cup B|}$$

系統自動比對並輸出符合該機械類別之法定操作人員資格要求（如「專任操作人員」、「每日作業前檢點」、「年度安全代檢合格」），同時導出 Jaccard 資格匹配指數與引用條文內容。

本 Skill 同時具備 **Guardrail 得分防呆機制**：當最高的 Jaccard 相似度得分低於指定門檻（`threshold`）時，自動觸發防呆保護並輸出固定提示，確保檢索與比對解答嚴格基於可追溯之事實（Grounded Sources）。

---

## 2. 輸入欄位 (Input Fields)

| 欄位名稱 | 型態 (Type) | 必填 | 預設值 | 說明 / 範例 |
| :--- | :--- | :--- | :--- | :--- |
| `equipment_type` | String | 否 | `"衝壓剪切機械"` | 選擇之危險性機械類別（例如：「衝壓剪切機械」、「升降機具」、「電動工具」） |
| `user_credentials` | Array (String) | 否 | `["專任操作人員", "每日作業前檢點"]` | 操作人員持有之證照或訓練憑證陣列 |
| `query_text` | String | 否 | `"衝壓機操作人員資格與每日作業前安全檢點規定"` | 使用者自然語言查詢字串 |
| `top_k` | Integer | 否 | `3` | 擷取最相似近鄰條文之數量 $K$ |
| `threshold` | Float | 否 | `0.20` | Guardrail 得分防呆門檻 (範圍 0.0 ~ 1.0) |
| `output_json_path` | String | 否 | `"/workspace/scratch/machine_qualification_match_result.json"` | 運算結果 JSON 檔案寫入路徑 |

---

## 3. 輸出欄位 (Output Fields)

| 欄位名稱 | 型態 (Type) | 說明 / 範例 |
| :--- | :--- | :--- |
| `status` | String | 執行狀態（例如 `"success"`） |
| `found` | Boolean | 是否成功命中有效資格條文（`true` / `false`） |
| `equipment_type` | String | 輸入之機械設備類別 |
| `user_credentials` | Array | 輸入之資格憑證清單 |
| `query` | String | 原始查詢字串 |
| `similarity_score` | Float | 最高匹配條文之 Jaccard 相似度得分 (0.0000 ~ 1.0000) |
| `jaccard_score` | Float | 最高匹配條文之 Jaccard 相似度得分 |
| `threshold` | Float | 套用之 Guardrail 得分門檻 |
| `answer_text` | String | 條理化解答卡片內文，或防呆提示文字 |
| `source_title` | String | 主要引用之法規名稱 |
| `source_url` | String | 引用來源檔案或 PDF 路徑 |
| `matched_qualifications` | Array | Top-K 匹配之操作資格詳細物件清單（未命中時為空陣列） |
| `steps` | Array | 演算法推導過程日誌陣列（供前端網頁「這個結果怎麼算的」區塊讀取顯示） |

---

## 4. 限制 (Constraints)

1. **純 Python 標準庫離線重現**：核心運算使用 Python 標準庫 (`re`, `json`)，無外部套件依賴，可離線執行。
2. **Guardrail 得分防呆**：當 `jaccard_score < threshold` 時，`found` 必須設為 `false`，且 `answer_text` 必須輸出固定防呆提示：`"查不到相關法規與案例資料。系統無法從目前收錄之製造知識庫中獲取足夠數據以回答此問題，請重新調整檢索關鍵字或機械類別。"`
3. **JSON 實體持久化與步驟日誌**：執行完畢後必須自動將成果寫入 `.json` 檔案，且 JSON 結構中必須包含 `steps` 陣列，詳細記錄每一個階段（設備類別預篩選、集合提取、Jaccard 相似度計算、KNN 排序與 Guardrail 得分檢核）之計算邏輯。

---

## 5. 詳細步驟 (Detailed Steps)

1. **步驟 1：資料庫載入與設備類別預篩選 (Categorical Pre-filtering)**：載入危險性機械操作資格資料庫，比對傳入之目標機械類別。
2. **步驟 2：查詢與憑證集合提取 (Set Extraction)**：將設備類別、持有的憑證清單與查詢文字進行清洗與 N-gram 集合提取。
3. **步驟 3：Jaccard 集合相似度矩陣計算 (Jaccard Similarity Calculation)**：
   $$J(A, B) = \frac{|A \cap B|}{|A \cup B|}$$
   套用交集與聯集基數比例計算特徵重疊度，若機械類別完全對齊則給予權重加成。
4. **步驟 4：KNN Top-K 近鄰排序 (KNN Distance Ranking)**：依 Jaccard 相似度得分降冪排序，採用 $K$ 近鄰邏輯擷取前 $K$ 筆得分最高的資格條文。
5. **步驟 5：Guardrail 門檻比對與 JSON 結果匯出 (Guardrail Evaluation & JSON Export)**：檢核得分是否 $\ge threshold$，組裝符合格式之 JSON 成果（含 `steps` 推導日誌）並持久化儲存。
