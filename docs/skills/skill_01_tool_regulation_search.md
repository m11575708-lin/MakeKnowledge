# SKILL: skill_01_tool_regulation_search

**name**: `skill_01_tool_regulation_search`  
**description**: 法規與 SOP 檢索：把問題轉成 TF-IDF 向量，用餘弦相似度找出最相關的 Top-K 條文，最高分低於門檻就回「查不到」。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 檢索 |
| 對應故事 | US-01、US-16 |
| 網頁 | 01 智慧問答、05 公開法規查詢 |
| 演算法 | KNN + 餘弦相似度（TF-IDF） |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 01 頁：skill_01 → AnythingLLM 產生回答；05 頁：skill_01（關鍵字查詢） |
| 程式檔 | `skills/skill_01_tool_regulation_search.py` |
| 主函式 | `search_tool_regulations()` |
| MCP 工具名 | `skill_01_tool_regulation_search` |

---

## 1. 做什麼

**使用者**：一般民眾與各工程師

使用者用口語提問（例如「工廠發生有人死亡的職災，要在幾小時內通報？」），Skill 動態掃描 `docs/` 資料夾內的每一份文件（目前為《職業安全衛生法》與《危險性機械及設備安全檢查規則》共 234 條，一條一檔），以 Unigram＋Bigram 切詞建立 TF-IDF 向量，計算查詢與每份文件的餘弦相似度，依分數排序取前 K 名（KNN）。最高分低於門檻時不硬答，回固定的「查不到」訊息，確保回答都有可追溯的條文來源。

**程式內的演算法流程**：動態掃描 docs/ 資料夾 -> TF-IDF 詞頻向量化 + 餘弦相似度 + KNN 排序 + Guardrail 防呆

---

## 2. 輸入

函式：`search_tool_regulations(query_text='', scope='all', top_k=3, threshold=0.1, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `query_text` | String | 是 | `''` | 使用者的自然語言問題；空字串會被 Guardrail 擋下 |
| `scope` | String | 否 | `'all'` | 檢索範圍：`all`（全部）、`regulations`（公開法規）、`repairs`（檔名含 sop 的文件；本版沒有這類文件，選此範圍會查不到） |
| `top_k` | Integer | 否 | `3` | 回傳前幾名（K） |
| `threshold` | Float | 否 | `0.1` | Guardrail 門檻（0–1），最高相似度低於此值回「查不到」 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "query_text": "工廠發生有人死亡的職災，要在幾小時內通報？"
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `query` | String | 原始查詢字串 | `工廠發生有人死亡的職災，要在幾小時內通報？` |
| `scope` | String | 實際套用的檢索範圍 | `all` |
| `similarity_score` | Float | 第 1 名的餘弦相似度（0–1） | `0.1285` |
| `threshold` | Float | 實際套用的門檻 | `0.1` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `依據《law_osh_act_art037.md》之規定：# 職業安全衛生法 第 37 條（第四章 監督與檢查）  1. 事業單位工作場所發…` |
| `source_title` | String | 第 1 名文件的檔名 | `law_osh_act_art037.md` |
| `source_url` | String | 第 1 名文件的連結（`/docs/<檔名>`） | `/docs/law_osh_act_art037.md` |
| `search_results` | Array | Top-K 文件清單（doc_id、類別、內容、相似度）；未命中時為空陣列 | `[{"doc_id": "law_osh_act_art037", "category": "regulations", …, …]`（共 3 筆） |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸出 `top_k_regulations`，程式實際用 `search_results`。


---

## 4. 限制

1. 只檢索 `docs/` 根目錄的 .md / .txt；本版未收錄 CNS 標準與廠內 SOP，問這兩類問題時正確行為是「查不到」。
2. TF-IDF 只看字詞重疊，不懂同義詞：口語問法和條文用字差很多時會排錯（skill_29 的 6 題未命中都屬此類）。
3. 預設門檻 0.10 偏低：附件 A-2 的 CNS 問題會以 0.115 命中一條不相關條文，報告中列為已知限制。
4. `docs/` 裡沒有文件時會回「動態載入 0 筆」並一律查不到；GitHub 上需附 234 個條文檔或 `tools/split_laws.py` 的產生步驟。
5. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
6. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `collections` | Python 標準函式庫 | PSF License 2.0 | 計數與分組 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

餘弦相似度與 Jaccard 屬 D-3 驗證計畫的「3–5 筆小資料手算」，【待補：手算紀錄】。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 動態掃描 docs/ 資料夾與載入檔案 | 成功掃描目標路徑 '/home/claude/work/skills/../docs'，動態載入 234 筆真實知識庫文件。 | Dynamic Directory File Scanner | os, io |
| 2 | 查詢字串 Token 向量化與分詞 | 對查詢字串 '工廠發生有人死亡的職災，要在幾小時內通報？' 進行正則清洗與 Bigram 切分，提取 19 個特徵 Token。 | Regular Expression Tokenization | re, collections |
| 3 | 餘弦相似度矩陣計算 | 計算動態載入之文件向量與查詢向量間之夾角餘弦值：cos(θ) = (A·B) / (\|\|A\|\|·\|\|B\|\|)。 | Cosine Similarity | math, collections.Counter |
| 4 | KNN Top-K 近鄰排序擷取 | 依餘弦相似度得分降冪排序，採用 K-Nearest Neighbors (K=3) 擷取得分最高之 Top-3 筆條文，最高相似度為 0.1285。 | K-Nearest Neighbors (KNN) | Python Built-in Sorting |
| 5 | Guardrail 得分防呆門檻比對與解答生成 | 防呆檢核狀態：PASSED (Score 0.1285 >= Threshold 0.1)。門檻極限值：0.1。依據檢核結果自動輸出 Grounded 條文解答卡片或防呆提示。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_01_tool_regulation_search import search_tool_regulations
result = search_tool_regulations(query_text='工廠發生有人死亡的職災，要在幾小時內通報？')
print(result["answer_text"])
```

本次結果（`guardrail_status`：`None`）：

> 依據《law_osh_act_art037.md》之規定：# 職業安全衛生法 第 37 條（第四章 監督與檢查）
> 
> 1. 事業單位工作場所發生職業災害，雇主應即採取必要之急救、搶救等措施，並會同勞工代表實施調查、分析及作成紀錄。
> 2. 事業單位勞動場所發生下列職業災害之一者，雇主應於八小時內通報勞動檢查機構：
> 一、發生死亡災害。
> 二、發生災害之罹災人數在三人以上。
> 三、發生災害之罹災人數在一人以上，且需住院治療。
> 四、其他經中央主管機關指定公告之災害。
> 3. 勞動檢查機構接獲前項報告後，應就工作場所發生死亡或重傷之災害派員檢查。
> 4. 事業單位發生第二項之災害，除必要之急救、搶救外，雇主非經司法機關或勞動檢查機構許可，不得移動或破壞現場。 （相關條文匹配相似度指數為 0.13）。

完整結果 JSON：`results/skill_01_tool_regulation_search_result.json`（2026-11-16 執行）。
