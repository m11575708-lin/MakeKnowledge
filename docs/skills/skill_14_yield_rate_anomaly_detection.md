# SKILL: skill_14_yield_rate_anomaly_detection

**name**: `skill_14_yield_rate_anomaly_detection`  
**description**: 批次品質異常偵測：以隨機森林（Bootstrap + 吉尼切分）對批次製程參數投票，判斷是否異常並估計良品機率。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-09 |
| 網頁 | 10 品質根因分析 |
| 演算法 | 隨機森林 |
| 講義週次 | 第 6 週 |
| 呼叫順序 | 10 頁：skill_14 → skill_15 → skill_16 |
| 程式檔 | `skills/skill_14_yield_rate_anomaly_detection.py` |
| 主函式 | `detect_yield_anomaly()` |
| MCP 工具名 | `skill_14_yield_rate_anomaly_detection` |

---

## 1. 做什麼

**使用者**：品質與製程工程師（良率下滑時）

以加熱溫度、冷卻水流量、軋延速度三個製程參數訓練多棵 CART（每棵樹用 Bootstrap 抽樣並隨機選特徵），對指定批次投票：超過半數判異常即為異常；不良機率 = 各樹葉節點不良比例的平均，估計良率 = 1 − 不良機率。同時報告 OOB 與保留集準確率，以及各批次的估計良率趨勢。

**程式內的演算法流程**：輸入防呆 -> 載入資料與切分 -> Bootstrap + Gini 建立多棵決策樹 -> 多樹投票與機率平均 -> Guardrail（模型品質／外插／投票邊界）

---

## 2. 輸入

函式：`detect_yield_anomaly(batch_params=None, batch_id=None, n_trees=100, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `batch_params` | Array[Float] | 否 | `None` | `[加熱溫度 °C, 冷卻水流量 L/min, 軋延速度 m/s]`；未提供時用 batch_id 的參數 |
| `batch_id` | String | 否 | `None` | 批次編號，例如 `B-2026-10` |
| `n_trees` | Integer | 否 | `100` | 樹的數量 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經直接呼叫）實際傳入的參數：

```json
{
  "batch_id": "B-2026-10"
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `batch_id` | String | 批次編號 | `B-2026-10` |
| `batch_params` | Array | 本次批次的製程參數 | `[189.5, 36.5, 16.3]` |
| `feature_names` | Array | 特徵的程式名稱，順序與輸入向量相同 | `["temp", "cooling", "speed"]` |
| `n_trees` | Integer | 隨機森林的樹數 | `100` |
| `yield_rate_prediction` | Float | 模型估計的良品機率（不是產線實測良率） | `0.0777` |
| `defect_probability` | Float | 不良機率 | `0.9223` |
| `ensemble_prediction` | Integer | 多數決結果：0 正常、1 異常 | `1` |
| `status_label` | String | 判定中文說明 | `QUALITY_ANOMALY` |
| `votes_anomaly` | Integer | 投異常的樹數 | `95` |
| `votes_total` | Integer | 總樹數 | `100` |
| `vote_fraction` | Float | 投異常的比例 | `0.95` |
| `model_metrics` | Object | 模型品質指標（OOB、保留集準確率等） | `{"oob_accuracy": 0.8542, "holdout_accuracy": 0.825, "majority_baseline…}` |
| `batch_trend` | Array | 各批次的估計良率與投票結果（畫趨勢圖用） | `[{"batch_id": "B-2026-01", "estimated_yield": 0.9588, "observ…, …]`（共 10 筆） |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=11，示範規則非真實產線)` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `預估良率 7.8%，判定為「品質異常」（95/100 棵樹投異常）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 沒有 `data/process_quality.csv` 時用模擬資料（seed=11，訓練 480、測試 120、10 個批次），規則是自訂的。
2. 估計良率是模型輸出的機率，不是實測良率；兩者不應混為一談。
3. 結果取決於亂數抽樣，對照程式無法重現同一片森林。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

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
| 1 | 批次參數與森林設定防呆 | 批次 B-2026-10 的製程參數：加熱溫度 189.5 °C、冷卻水流量 36.5 L/min、軋延速度 16.3 m/min，皆為合理範圍內的有限數值；森林樹數量 N=100（允許 10–300）。 | Boundary & Type Validation | math, re |
| 2 | 載入製程資料與訓練／測試切分 | 資料來源：synthetic_demo (seed=11，示範規則非真實產線)；共 600 筆，不良率 39.8%。以固定 seed 切分：訓練 480 筆、測試 120 筆（20%，不參與訓練）。 | Train/Test Holdout Split (80/20) | csv, random |
| 3 | Bootstrap 自助抽樣建立多棵決策樹 | 建立 100 棵 CART 決策樹：每棵以 Bootstrap（有放回抽樣 480 筆）訓練，每個節點僅隨機考慮 2 個特徵，依吉尼不純度 I_G = 1 - Σp² 下降量最大者切分（最大深度 6、葉節點至少 5 筆；前 20 棵實際深度 6–6）。OOB（袋外）準確率 85.4%、測試集準確率 82.5%（「永遠猜多數類」的基準為 60.2%）。 | Random Forest (Bootstrap + Gini Impurity) | random |
| 4 | 多樹投票與良率機率平均 | 100 棵樹中 95 棵投「異常」、5 棵投「正常」（95.0%）；多數決（>50%）→ 1（品質異常）。各樹葉節點不良比例平均 = 0.9223，預估良率 = 1 - 0.9223 = 7.8%。 | Ensemble Majority Voting & Probability Averaging | Python Built-in |
| 5 | 模型品質與外插 Guardrail 檢核 | 防呆檢核狀態：PASSED（OOB 85.4% ≥ 70%、測試集 82.5% ≥ 70% 且優於多數類基準、輸入未嚴重外插）。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_14_yield_rate_anomaly_detection import detect_yield_anomaly
result = detect_yield_anomaly(batch_id='B-2026-10')
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 預估良率 7.8%，判定為「品質異常」（95/100 棵樹投異常）。

完整結果 JSON：`results/skill_14_yield_rate_anomaly_detection_result.json`（2026-11-16 執行）。
