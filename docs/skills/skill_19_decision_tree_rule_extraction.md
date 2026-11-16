# SKILL: skill_19_decision_tree_rule_extraction

**name**: `skill_19_decision_tree_rule_extraction`  
**description**: 決策樹剪枝與白盒規則：以代價複雜度剪枝縮小樹，並把每條路徑轉成可讀的 IF-THEN 規則，比較剪枝前後準確率。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-11 |
| 網頁 | 11 鋼板缺陷分類 |
| 演算法 | 代價複雜度剪枝 + IF-THEN 規則 |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 11 頁：skill_17 → skill_18 → skill_19 |
| 程式檔 | `skills/skill_19_decision_tree_rule_extraction.py` |
| 主函式 | `extract_decision_tree_rules()` |
| MCP 工具名 | `skill_19_decision_tree_rule_extraction` |

---

## 1. 做什麼

**使用者**：品質與製程工程師（要把模型交給現場當判讀規則）

代價複雜度 R_α(T) = R(T) + α|T|（R 為訓練集誤分類比例，|T| 為葉節點數），以最弱連結法產生剪枝序列，依使用者的 α（或驗證集建議的 α）選樹。剪枝後每條根到葉的路徑轉成一條 IF-THEN 規則；若有輸入缺陷特徵，會標出本次符合的規則。三份資料分工：訓練集長樹、驗證集建議 α、測試集只用來報告剪枝前後準確率。

**程式內的演算法流程**：α 與前置檢核 -> 最弱連結剪枝序列 (g(t)) -> 選樹（使用者 α 或驗證集建議 α） -> 路徑轉 IF-THEN 規則 -> 測試集剪枝前後比較與 Guardrail

---

## 2. 輸入

函式：`extract_decision_tree_rules(alpha_threshold=0.01, area=None, aspect_ratio=None, contrast=None, auto_alpha=False, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `alpha_threshold` | Float | 否 | `0.01` | 剪枝強度 α（合理範圍約 0–0.1；超過 0.15 樹會只剩 1–2 葉） |
| `area` | Float | 否 | `None` | 缺陷面積；有提供三項特徵時會標出本次符合的規則 |
| `aspect_ratio` | Float | 否 | `None` | 長寬比 |
| `contrast` | Float | 否 | `None` | 灰階對比度 |
| `auto_alpha` | Boolean | 否 | `False` | 是否改用驗證集建議的 α |
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
| `pruning_status` | String | 剪枝狀態 | `COMPLETED` |
| `alpha_used` | Float | 實際使用的 α | `0.01` |
| `alpha_recommended` | Float | 驗證集建議的 α | `0.00278` |
| `auto_alpha` | Boolean | 是否使用建議 α | `false` |
| `rule_path` | null | 本次缺陷符合的規則（未輸入特徵時為 null） | `null` |
| `pruned_defect_class` | null | 剪枝後樹的判定類別（未輸入特徵時為 null） | `null` |
| `rules` | Array | 全部 IF-THEN 規則與測試支持數 | `[{"rule_id": 1, "text": "IF area ≤ 151.45 AND aspect_ratio ≤ …, …]`（共 6 筆） |
| `accuracy_before` | Float | 剪枝前測試準確率 | `0.9` |
| `accuracy_after` | Float | 剪枝後測試準確率 | `0.8667` |
| `accuracy_validation_after` | Float | 剪枝後驗證準確率 | `0.8333` |
| `accuracy_train_after` | Float | 剪枝後訓練準確率 | `0.9083` |
| `leaves_before` | Integer | 剪枝前葉節點數 | `29` |
| `leaves_after` | Integer | 剪枝後葉節點數 | `6` |
| `confusion_matrix_before` | Array | 剪枝前混淆矩陣 | `[[25, 2, 0, 3], [2, 28, 0, 0], [2, 0, 28, 0], [3, 0, 0, 27]]` |
| `confusion_matrix_after` | Array | 剪枝後混淆矩陣 | `[[26, 2, 0, 2], [6, 24, 0, 0], [4, 0, 26, 0], [2, 0, 0, 28]]` |
| `class_names` | Array | 類別代碼（英文），與混淆矩陣列欄順序相同 | `["Scratch", "Crack", "Inclusion", "Scale"]` |
| `class_labels` | Array | 類別中文名稱 | `["劃痕", "裂紋", "夾雜", "氧化皮"]` |
| `alpha_curve` | Array | 各 α 的葉節點數與訓練、驗證準確率 | `[{"alpha": 0.0, "leaves": 22, "train_accuracy": 0.9778, "val_…, …]`（共 10 筆） |
| `n_test` | Integer | 測試集筆數 | `120` |
| `tree` | Object | 剪枝後的樹（巢狀物件，畫樹狀圖用） | `{"id": 0, "leaf": false, "n": 360, "counts": {"Scratch": 90, "Crack": …}` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=31，示範分佈非真實鋼板資料)` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["規則 1 的訓練支持樣本少於 5 筆，不穩定"]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `剪枝後保留 6 個葉節點（原 29），共 6 條規則；測試集準確率 90.0% → 86.7%。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 規格書寫「以測試集選 α」，本 Skill 改用驗證集選 α，避免用同一份測試集同時選模型與報告準確率而高估。
2. 測試集約 120 筆，1 筆約 0.8 個百分點；剪枝前後差距小於 2 個百分點不具統計意義。
3. 剪枝未與課堂工具比對（課堂沒有教剪枝）。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `copy` | Python 標準函式庫 | PSF License 2.0 | 深層複製 |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `hashlib` | Python 標準函式庫 | PSF License 2.0 | SHA-256 去重 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| 專案內模組 | — | 本專案 | `_cart`, `_common`, `_forest`, `_steel_model` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

根節點切分對照 `tree.py grow --crit gini`（見 skill_17）；剪枝課堂未教，未比對。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

本 Skill 沒有獨立的比對列，說明見上。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 剪枝係數 α 與輸入前置檢核 | α = 0.01（允許 0–1）；使用者指定 α。未提供單一缺陷，只導出整體規則。 | Boundary & Type Validation | math |
| 2 | 建立最弱連結剪枝序列 | 完整樹 29 個葉節點。對每個內部節點 t 計算 g(t) = (R(t) - R(T_t)) / (\|T_t\| - 1)（R 為誤分類比例，N=360），反覆剪掉 g 最小的節點，得到 24 棵巢狀子樹；其中不同 α 可到達的有 10 棵，α 序列 0.0000(22葉) → 0.0014(20葉) → 0.0028(16葉) → 0.0042(12葉) → 0.0056(8葉) → 0.0083(6葉) …（非遞減）。 | Cost-Complexity Pruning (Weakest-link g(t)) | copy |
| 3 | 以驗證集建議 α 並選定剪枝後的樹 | 驗證集準確率最高的可到達子樹：α=0.0028、16 個葉節點、驗證準確率 89.2%（同分取較大 α＝較小的樹）→ 建議 α。本次採用 α=0.0100，選出 6 個葉節點的子樹（訓練 90.8%、驗證 83.3%）。 | Minimal Cost-Complexity Subtree  R_α(T)=R(T)+α\|T\| | Python Built-in |
| 4 | 樹路徑轉白盒 IF-THEN 規則 | 剪枝後的樹有 6 個葉節點，對應 6 條規則；每條根到葉的路徑轉成 IF-THEN，同一特徵的多個條件合併為最緊的上下界。 | Rule Extraction from Root-to-Leaf Paths | Python Built-in |
| 5 | 測試集剪枝前後比較與 Guardrail 檢核 | 測試集（120 筆，未參與選 α）：剪枝前 90.0%（29 葉）→ 剪枝後 86.7%（6 葉），差 -3.3 個百分點。防呆檢核狀態：PASSED_WITH_WARNINGS（剪枝後模型品質通過）。規則 1 的訓練支持樣本少於 5 筆，不穩定 | Held-out Test Evaluation & Guardrail | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_19_decision_tree_rule_extraction import extract_decision_tree_rules
result = extract_decision_tree_rules()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 剪枝後保留 6 個葉節點（原 29），共 6 條規則；測試集準確率 90.0% → 86.7%。

完整結果 JSON：`results/skill_19_decision_tree_rule_extraction_result.json`（2026-11-16 執行）。
