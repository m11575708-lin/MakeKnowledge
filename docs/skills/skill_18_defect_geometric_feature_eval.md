# SKILL: skill_18_defect_geometric_feature_eval

**name**: `skill_18_defect_geometric_feature_eval`  
**description**: 缺陷特徵影響力評估：以決策樹的吉尼重要度算出面積、長寬比、對比度各自的影響力，並用排列重要度交叉檢查。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-10 |
| 網頁 | 11 鋼板缺陷分類 |
| 演算法 | 決策樹吉尼重要度 |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 11 頁：skill_17 → skill_18 → skill_19 |
| 程式檔 | `skills/skill_18_defect_geometric_feature_eval.py` |
| 主函式 | `evaluate_defect_features()` |
| MCP 工具名 | `skill_18_defect_geometric_feature_eval` |

---

## 1. 做什麼

**使用者**：品質與製程工程師

特徵影響力 = 該特徵在樹中所有切分節點的 (n_t / N)·ΔGini 加總，再歸一化為總和 1（與 skill_15 的 MDI 同概念，作用在單棵 CART）。另在測試集打亂單一特徵、重複 5 次平均準確率下降量，作為排列重要度交叉檢查。

**程式內的演算法流程**：模型檢核 -> 逐節點吉尼下降量 -> 歸一化為特徵影響力 -> 測試集排列重要度交叉檢查 -> Guardrail

---

## 2. 輸入

函式：`evaluate_defect_features(model_id='CART_DEFECT_V1', output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `model_id` | String | 否 | `'CART_DEFECT_V1'` | 要評估的模型代碼（目前只有 `CART_DEFECT_V1`） |
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
| `model_id` | String | 模型代碼 | `CART_DEFECT_V1` |
| `feature_importance` | Object | 各特徵的吉尼重要度（總和 1） | `{"area": 0.134, "aspect_ratio": 0.3419, "contrast": 0.5241}` |
| `ranking` | Array | 排名、重要度、使用的切分次數與排列重要度 | `[{"rank": 1, "feature": "contrast", "label": "灰階對比度", "import…, …]`（共 3 筆） |
| `top_feature` | String | 影響力最大的特徵 | `contrast` |
| `top_feature_label` | String | 影響力最大特徵的中文名稱 | `灰階對比度` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=31，示範分佈非真實鋼板資料)` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["吉尼影響力最高的是「灰階對比度」，但排列重要度最高的是「長寬比」，兩種方法明顯不一致，請謹慎解讀", …]`（共 2 筆） |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `影響力最高的是「灰階對比度」（52%），其次為「長寬比」（34%）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 吉尼重要度與排列重要度排名不一致（吉尼：對比度第一；排列：長寬比第一），報告中列為已知限制。
2. 重要度描述的是模型怎麼用特徵，不代表物理因果；單棵樹對訓練資料很敏感。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

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

根節點切分與 skill_17 共用同一棵樹，對照結果見 skill_17。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

本 Skill 沒有獨立的比對列，說明見上。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 模型編號與前置檢核 | 模型 CART_DEFECT_V1 存在（資料：synthetic_demo (seed=31，示範分佈非真實鋼板資料)；完整樹 29 個葉節點、28 次切分、訓練 360 筆）。 | Boundary & Type Validation | math |
| 2 | 逐節點計算吉尼下降量 | 走訪每個切分節點，計算 ΔGini = n_t·I(t) - n_l·I(l) - n_r·I(r)，除以訓練總數 N 後累加到該節點使用的特徵：缺陷面積 用於 12 次切分、累計 0.0971；長寬比 用於 9 次切分、累計 0.2479；灰階對比度 用於 7 次切分、累計 0.3800（根節點吉尼 0.750）。 | Gini Impurity Decrease per Split  ΔI = I(t) - Σ(n_c/n_t)·I(c) | Python Built-in |
| 3 | 歸一化為特徵影響力 | 歸一化（÷ 總下降量 0.7250）：灰階對比度 0.524、長寬比 0.342、缺陷面積 0.134（總和 1.000）。 | Gini-based Feature Importance (normalized) | Python Built-in |
| 4 | 測試集排列重要度交叉檢查 | 測試集基準準確率 90.0%；逐一打亂單一特徵（各 5 次平均）後準確率下降：缺陷面積 +16.3 個百分點、長寬比 +36.0 個百分點、灰階對比度 +27.2 個百分點；排列法最重要者為「長寬比」。 | Permutation Importance Cross-check | random |
| 5 | 模型品質與影響力分布 Guardrail 檢核 | 防呆檢核狀態：PASSED_WITH_WARNINGS（模型品質通過、影響力總和為 1）。吉尼影響力最高的是「灰階對比度」，但排列重要度最高的是「長寬比」，兩種方法明顯不一致，請謹慎解讀 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_18_defect_geometric_feature_eval import evaluate_defect_features
result = evaluate_defect_features()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 影響力最高的是「灰階對比度」（52%），其次為「長寬比」（34%）。

完整結果 JSON：`results/skill_18_defect_geometric_feature_eval_result.json`（2026-11-16 執行）。
