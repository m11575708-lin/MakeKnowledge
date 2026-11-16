# SKILL: skill_17_steel_surface_defect_classify

**name**: `skill_17_steel_surface_defect_classify`  
**description**: 鋼板表面缺陷分類：以 CART 決策樹（吉尼切分）依面積、長寬比、對比度把缺陷分成劃痕、裂紋、夾雜、氧化皮四類。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-10 |
| 網頁 | 11 鋼板缺陷分類 |
| 演算法 | CART 決策樹 |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 11 頁：skill_17 → skill_18 → skill_19 |
| 程式檔 | `skills/skill_17_steel_surface_defect_classify.py` |
| 主函式 | `classify_steel_defect()` |
| MCP 工具名 | `skill_17_steel_surface_defect_classify` |

---

## 1. 做什麼

**使用者**：品質與製程工程師（發現缺陷時）

分層切分資料後以吉尼不純度遞迴建樹（完整、未剪枝），沿決策路徑分類本次缺陷，預測類別為葉節點多數類。同時輸出決策路徑、葉節點純度、測試集混淆矩陣（列＝真實、欄＝預測）、各類召回率，以及訓練與測試準確率（差距大代表過度擬合）。

**程式內的演算法流程**：輸入防呆 -> 載入資料與分層切分 -> CART 吉尼切分遞迴建樹 -> 沿決策路徑分類並彙整測試集混淆矩陣 -> Guardrail

---

## 2. 輸入

函式：`classify_steel_defect(area=150, aspect_ratio=4.2, contrast=85, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `area` | Float | 否 | `150` | 缺陷面積（mm²） |
| `aspect_ratio` | Float | 否 | `4.2` | 長寬比 |
| `contrast` | Float | 否 | `85` | 灰階對比度 |
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
| `features` | Array | 本次輸入的特徵值 | `[150.0, 4.2, 85.0]` |
| `feature_names` | Array | 特徵的程式名稱，順序與輸入向量相同 | `["area", "aspect_ratio", "contrast"]` |
| `defect_class` | String | 預測類別代碼 | `Scratch` |
| `defect_class_label` | String | 預測類別中文名稱 | `劃痕` |
| `class_probabilities` | Object | 葉節點內各類別的訓練樣本比例（不是校準過的機率） | `{"Scratch": 1.0, "Crack": 0.0, "Inclusion": 0.0, "Scale": 0.0}` |
| `leaf_samples` | Integer | 葉節點樣本數 | `40` |
| `leaf_purity` | Float | 葉節點純度 | `1.0` |
| `decision_path` | Array | 本次走過的每個切分條件 | `[{"feature": "aspect_ratio", "label": "長寬比", "op": ">", "thre…, …]`（共 5 筆） |
| `class_names` | Array | 類別代碼（英文），與混淆矩陣列欄順序相同 | `["Scratch", "Crack", "Inclusion", "Scale"]` |
| `class_labels` | Array | 類別中文名稱 | `["劃痕", "裂紋", "夾雜", "氧化皮"]` |
| `confusion_matrix` | Array | 測試集混淆矩陣 | `[[25, 2, 0, 3], [2, 28, 0, 0], [2, 0, 28, 0], [3, 0, 0, 27]]` |
| `per_class_recall` | Array | 各類召回率 | `[0.8333, 0.9333, 0.9333, 0.9]` |
| `accuracy_train` | Float | 訓練集準確率 | `0.9778` |
| `accuracy_test` | Float | 測試集準確率 | `0.9` |
| `majority_baseline` | Float | 全部猜多數類的準確率（基準） | `0.25` |
| `n_leaves` | Integer | 葉節點數 | `29` |
| `tree_depth` | Integer | 樹深度 | `9` |
| `n_test` | Integer | 測試集筆數 | `120` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=31，示範分佈非真實鋼板資料)` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `判定為「Scratch（劃痕）」，所在葉節點純度 100%；完整樹測試集準確率 90.0%。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 沒有 `data/steel_defects.csv` 時用模擬資料（seed=31，4 類 × 150 筆，測試 120 筆）。
2. 完整樹 29 葉，容易過度擬合；剪枝由 skill_19 負責。
3. 講義 tree.py 範例用熵，本 Skill 的 CART 用吉尼；兩者切點可能不同。
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

對照 `tree.py grow --crit gini`（講義第 6 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| 根節點欄位 | aspect_ratio | aspect_ratio | 一致 |  |
| 根節點切點 | 3.055 | 3.055 | 一致 | 講義：相鄰兩值的中點 |
| 根節點吉尼下降 | 0.205419 | 0.205419 | 一致 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 缺陷特徵輸入防呆 | 特徵：缺陷面積 150mm²、長寬比 4.2、灰階對比度 85，皆為合理範圍內的有限數值（面積 >0、長寬比 ≥1、對比度 0–255）。 | Boundary & Type Validation | math |
| 2 | 載入缺陷資料與分層切分 | 資料來源：synthetic_demo (seed=31，示範分佈非真實鋼板資料)；共 600 筆、4 類（Scratch、Crack、Inclusion、Scale）。依類別分層切分：訓練 360、驗證 120、測試 120 筆（60%/20%/20%，固定 seed）；測試集不參與任何選擇。 | Stratified Train/Validation/Test Split (60/20/20) | csv, random |
| 3 | CART 吉尼切分遞迴建樹 | 以吉尼不純度 I_G = 1 - Σp² 遞迴切分：每個節點掃描全部 3 個特徵的所有相鄰值中點，選吉尼下降最大者（最大深度 10、葉節點至少 2 筆）。長出完整樹：29 個葉節點、深度 9、28 次切分；訓練準確率 97.8%、測試準確率 90.0%。 | CART Decision Tree (Gini Impurity Split) | Python Built-in |
| 4 | 沿決策路徑分類並彙整混淆矩陣 | 決策路徑：長寬比 4.2 > 3.05 → 灰階對比度 85 ≤ 110.85 → 缺陷面積 150 > 114.75 → 缺陷面積 150 ≤ 245.45 → 缺陷面積 150 ≤ 180.75；落入葉節點（40 筆訓練樣本：Scratch 40），多數類 → Scratch（劃痕）。測試集混淆矩陣（列＝真實、欄＝預測）對角線共 108/120 筆正確。 | Tree Traversal Classification & Confusion Matrix | Python Built-in |
| 5 | 模型品質與外插 Guardrail 檢核 | 防呆檢核狀態：PASSED（測試集準確率 90.0% ≥ 70% 且高於多數類基準 25.0% 達 10 個百分點、輸入未嚴重外插）。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_17_steel_surface_defect_classify import classify_steel_defect
result = classify_steel_defect()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 判定為「Scratch（劃痕）」，所在葉節點純度 100%；完整樹測試集準確率 90.0%。

完整結果 JSON：`results/skill_17_steel_surface_defect_classify_result.json`（2026-11-16 執行）。
