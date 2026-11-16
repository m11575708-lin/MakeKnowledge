# SKILL: skill_25_factory_risk_dendrogram_eval

**name**: `skill_25_factory_risk_dendrogram_eval`  
**description**: 樹狀圖切割與預防維護排程：依距離門檻切開 skill_24 的樹得到風險階層，依風險高低排出每週保養的設備。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-15 |
| 網頁 | 13 生產指數與維護 |
| 演算法 | Dendrogram 切割與評估 |
| 講義週次 | 第 7 週（延伸） |
| 呼叫順序 | 13 頁：skill_24 → skill_25 |
| 程式檔 | `skills/skill_25_factory_risk_dendrogram_eval.py` |
| 主函式 | `evaluate_dendrogram()` |
| MCP 工具名 | `skill_25_factory_risk_dendrogram_eval` |

---

## 1. 做什麼

**使用者**：生產排程主管 / 廠長（排保養窗口）

合併距離 ≤ 門檻的合併全部採用，剩下的連通群就是風險階層；未給門檻時取最後 8 次合併中最大高度落差的中點。群風險分數 = 群內設備風險 z 分數的平均，依此分高／中／低（相對排名）。排程規則：依群風險、群內個別風險排序，每週最多保養 capacity_per_week 台。另以輪廓係數與門檻到最近合併高度的距離評估切割可信度。

**程式內的演算法流程**：輸入與樹驗證 -> 依距離門檻切樹 -> 各群風險分數與分級 -> 預防維護排程 -> 切割可信度 Guardrail 與風險摘要

---

## 2. 輸入

函式：`evaluate_dendrogram(distance_threshold=None, hierarchy=None, equipment_rows=None, capacity_per_week=3, start_week=1, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `distance_threshold` | Float | 否 | `None` | 切樹的距離門檻；未提供時自動決定 |
| `hierarchy` | Object | 否 | `None` | skill_24 的結果；未提供時重算 |
| `equipment_rows` | Array[Object] | 否 | `None` | 設備資料（ID、區域、各指標） |
| `capacity_per_week` | Integer | 否 | `3` | 每週最多保養幾台 |
| `start_week` | Integer | 否 | `1` | 排程從第幾週開始 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "distance_threshold": null,
  "hierarchy": "<skill_24 的完整結果>",
  "equipment_rows": "<18 筆資料>",
  "capacity_per_week": 3
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `clusters_count` | Integer | 風險階層數 | `2` |
| `threshold_used` | Float | 實際使用的門檻 | `2.4426` |
| `threshold_auto` | Boolean | 門檻是否自動決定 | `true` |
| `labels` | Array | 每台設備的群編號 | `[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2]` |
| `groups` | Array | 各群的風險等級、台數、風險分數與成員 | `[{"group": 1, "tier": "高風險", "size": 12, "risk_score": 0.5657…, …]`（共 2 筆） |
| `dendrogram_tree` | Object | 樹狀圖（巢狀物件，畫圖用） | `{"node_id": 34, "height": 3.047826, "size": 18, "children": [{"node_id…}` |
| `preventive_schedule` | Array | 各群的保養起訖週與每台設備的保養週 | `[{"group": 1, "tier": "高風險", "action_week": 1, "end_week": 4,…, …]`（共 2 筆） |
| `weeks_total` | Integer | 排程總週數 | `6` |
| `capacity_per_week` | Integer | 每週保養台數上限 | `3` |
| `start_week` | Integer | 起始週 | `1` |
| `risk_summary` | String | 風險摘要（只陳述資料算得出的事實） | `高風險群含 12 台（EQ-PRESS-02、EQ-PRESS-03、EQ-PRESS-01、EQ-PRESS-06、EQ-PRESS-04…` |
| `silhouette` | Float | 切割後的平均輪廓係數 | `0.5482` |
| `threshold_gap` | Object | 門檻上下最近的合併高度 | `{"below": 1.837379, "above": 3.047826}` |
| `max_merge_height` | Float | 最後一次合併的高度 | `3.047826` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["風險層級是這批設備之間的相對排名，不是絕對的危險程度", …]`（共 2 筆） |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `切成 2 個風險階層，高風險群 12 台，預防維護共 6 週。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 風險等級是這批設備之間的相對排名：全部設備都健康時，排第一的群仍會被標成「高風險」。
2. 排程是簡單規則（單一班組、不考慮停機窗口、備品與人力），實際排程須由主管依現場調整。
3. 預設自動門檻切成 2 個階層（高風險 12 台）；13 頁截圖的設定切成 3 個階層（高風險 7 台），報告中引用數字時要註明門檻。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| 專案內模組 | — | 本專案 | `_common`, `_equipment_data`, `_hier`, `_kmeans`, `_spc_data`, `skill_24_preventive_maintenance_hierarchy` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

切樹以 skill_24 的合併高度為準，對照結果見 skill_24。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

本 Skill 沒有獨立的比對列，說明見上。

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入與階層樹驗證 | 階層樹含 18 台設備、17 次合併（最大高度 3.048）；距離門檻 2.443（未指定，取最後幾次合併最大高度落差的中點）；每週保養上限 3 台。 | Boundary & Type Validation (threshold, tree integrity) | math |
| 2 | 依距離門檻切割樹 | 採用合併距離 ≤ 2.443 的 16 次合併（共 17 次），其餘 1 次不合併 → 切成 2 個風險階層。 | Dendrogram Cut at Distance Threshold (merge height ≤ threshold) | Python Built-in |
| 3 | 計算各群風險分數與分級 | 群風險分數 = 群內各設備「風險方向 z 分數」跨指標平均後再取群平均；由高到低排序並標示相對風險層級：群1（高風險）12 台、分數 +0.57；群2（低風險）6 台、分數 -1.13。 | Mean Risk Score & Relative Ranking | math |
| 4 | 建立預防維護排程 | 排程：設備依「群風險高→低、群內風險高→低」排序，每週最多 3 台，自第 1 週起共需 6 週；群1：第 1–4 週；群2：第 5–6 週。 | Priority Scheduling (risk desc, weekly capacity) | Python Built-in |
| 5 | 切割可信度 Guardrail 與風險摘要 | 切割評估：平均輪廓係數 0.548；門檻下方最近的合併高度 1.837、上方 3.048。防呆檢核狀態：PASSED_WITH_WARNINGS。風險層級是這批設備之間的相對排名，不是絕對的危險程度；排程為單一班組、依風險排序的簡化規則，未考慮停機窗口、備品與人力，需由主管調整 | Silhouette & Cut-robustness Guardrail | math |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
# ... 代表網頁 API 傳入的大型資料（矩陣、前一個 Skill 的結果），由該頁 API 從模擬資料或前一步產生
from skill_25_factory_risk_dendrogram_eval import evaluate_dendrogram
result = evaluate_dendrogram(distance_threshold=None, hierarchy=..., equipment_rows=..., capacity_per_week=3)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 切成 2 個風險階層，高風險群 12 台，預防維護共 6 週。

完整結果 JSON：`results/skill_25_factory_risk_dendrogram_eval_result.json`（2026-11-16 執行）。
