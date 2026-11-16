# SKILL: skill_15_feature_importance_ranking

**name**: `skill_15_feature_importance_ranking`  
**description**: 品質參數重要度排序：以隨機森林的吉尼不純度下降量（MDI）排序哪個製程參數最影響品質，並用排列重要度交叉檢查。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-09 |
| 網頁 | 10 品質根因分析 |
| 演算法 | 隨機森林 MDI（吉尼重要度） |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 10 頁：skill_14 → skill_15 → skill_16 |
| 程式檔 | `skills/skill_15_feature_importance_ranking.py` |
| 主函式 | `rank_feature_importance()` |
| MCP 工具名 | `skill_15_feature_importance_ranking` |

---

## 1. 做什麼

**使用者**：品質與製程工程師

每個切分節點貢獻 (n_t / N)·ΔGini，同一特徵加總後在單棵樹內歸一化，再對所有樹平均。因 MDI 偏向取值多的連續特徵且以訓練資料計算，另在測試集算排列重要度（打亂單一特徵後準確率下降多少）交叉檢查，兩者第一名不一致時警告。

**程式內的演算法流程**：輸入防呆 -> 載入資料與森林 -> 累加各節點吉尼不純度下降量 -> 跨樹平均並歸一化排序 -> Guardrail（模型品質、與排列重要度交叉檢查）

---

## 2. 輸入

函式：`rank_feature_importance(batch_id=None, n_trees=100, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `batch_id` | String | 否 | `None` | 批次編號（只用於標示，重要度是全域的） |
| `n_trees` | Integer | 否 | `100` | 樹的數量 |
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
| `batch_id` | null | 批次編號 | `null` |
| `n_trees` | Integer | 隨機森林的樹數 | `100` |
| `feature_importance` | Array | 各參數的排名、MDI 重要度、標準差與排列重要度 | `[{"rank": 1, "feature": "temp", "label": "加熱溫度", "unit": "°C"…, …]`（共 3 筆） |
| `top_feature` | String | 最重要的參數 | `temp` |
| `top_feature_label` | String | 最重要參數的中文名稱 | `加熱溫度` |
| `importance_sum` | Float | 重要度總和（應為 1） | `1.0` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=11，示範規則非真實產線)` |
| `model_metrics` | Object | 模型品質指標（OOB、保留集準確率等） | `{"oob_accuracy": 0.8542, "holdout_accuracy": 0.825}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `MDI 排名第一的製程參數是「加熱溫度」（重要度 0.41），其次為「冷卻水流量」（0.39）。這代表模型整體最依賴這個參數來區分良品與異常…` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 重要度是全域的，只說明模型依賴哪個參數，不代表某一批異常的原因；單一批次的歸因由 skill_16 處理。
2. 模擬資料與亂數限制同 skill_14。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `hashlib` | Python 標準函式庫 | PSF License 2.0 | SHA-256 去重 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| `re` | Python 標準函式庫 | PSF License 2.0 | 正則表達式 |
| 專案內模組 | — | 本專案 | `_common`, `_forest`, `_quality_data`, `_quality_model` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

講義工具為 `forest.py compare`（第 6 週）；因結果取決於亂數，無法比對。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

本 Skill 沒有獨立的比對列，說明見上。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 批次與森林設定防呆 | 批次 （未指定，使用全部歷史資料）；森林樹數量 N=100。特徵重要度是以整份歷史資料訓練的森林計算，與批次參數無關，批次僅供標示。 | Boundary & Type Validation | math, re |
| 2 | 載入森林與各節點 Gini 下降量 | 載入 100 棵樹（資料：synthetic_demo (seed=11，示範規則非真實產線)，訓練 480 筆），共 1857 個切分節點（平均每棵 18.6 個）。對每個切分節點計算 (n_t/N)·[I(t) - n_l/n_t·I(l) - n_r/n_t·I(r)]，其中 I = 1 - Σp²，並累加到該節點使用的特徵上。 | Gini Impurity Decrease per Split  ΔI = I(t) - Σ(n_c/n_t)·I(c) | random |
| 3 | 跨樹平均並歸一化（MDI） | 各樹內先將特徵貢獻歸一化為總和 1，再對 100 棵樹取平均：加熱溫度 0.406、冷卻水流量 0.386、軋延速度 0.208（總和 1.000）；跨樹標準差 0.070、0.057、0.060。 | Mean Decrease Impurity (MDI) | Python Built-in |
| 4 | 排序並以排列重要度交叉檢查 | 依 MDI 由大到小排序：加熱溫度(0.406) > 冷卻水流量(0.386) > 軋延速度(0.208)。交叉檢查（測試集排列重要度＝打亂該特徵後準確率下降）：加熱溫度 +0.143、冷卻水流量 +0.113、軋延速度 +0.030，排列法最重要者為「加熱溫度」。 | Feature Ranking & Permutation Importance Cross-check | random |
| 5 | 模型品質與重要度分布 Guardrail 檢核 | 防呆檢核狀態：PASSED（測試集準確率 82.5% ≥ 70%、重要度總和為 1）。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_15_feature_importance_ranking import rank_feature_importance
result = rank_feature_importance()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> MDI 排名第一的製程參數是「加熱溫度」（重要度 0.41），其次為「冷卻水流量」（0.39）。這代表模型整體最依賴這個參數來區分良品與異常，不等同於單一批次的根因。

完整結果 JSON：`results/skill_15_feature_importance_ranking_result.json`（2026-11-16 執行）。
