# SKILL: skill_20_process_parameter_kmeans

**name**: `skill_20_process_parameter_kmeans`  
**description**: 製程參數分群：以 K-Means（k-means++ 多起點 + Lloyd 迭代）把製程溫度與壓力的 z 分數分成 K 群，並報告 SSE、群大小與輪廓係數。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-12 |
| 網頁 | 12 製程分群與 SPC |
| 演算法 | K 平均分群 |
| 講義週次 | 第 7 週 |
| 呼叫順序 | 12 頁：skill_21 → skill_20 → skill_22 |
| 程式檔 | `skills/skill_20_process_parameter_kmeans.py` |
| 主函式 | `run_kmeans()` |
| MCP 工具名 | `skill_20_process_parameter_kmeans` |

---

## 1. 做什麼

**使用者**：品質與製程工程師（監控製程狀態）

以 k-means++ 選初始中心並跑多組起點，Lloyd 迭代交替做「指派到最近中心」與「中心 = 群內平均」直到收斂，取 SSE 最小的一組。群依中心第一個座標由小到大重新編號，讓結果穩定。另輸出群大小、變異解釋率與輪廓係數。

**程式內的演算法流程**：輸入防呆 -> k-means++ 初始化（多起點） -> Lloyd 迭代（指派 + 更新 μ_k = 群內平均） -> SSE／群大小／變異解釋率／輪廓係數 -> Guardrail

---

## 2. 輸入

函式：`run_kmeans(z_scores=None, k=3, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `z_scores` | Array[Array[Float]] | 是 | — | n × d 的 z 分數矩陣（12 頁用 300 筆 × 2 維：temp_z、press_z） |
| `k` | Integer | 否 | `3` | 群數（12 頁預設由 skill_21 建議） |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "z_scores": "<300x2 陣列>",
  "k": 3
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `k` | Integer | 群數 | `3` |
| `cluster_centers` | Array | 各群中心（z 分數） | `[[-1.2648, 1.1741], [-0.2509, -1.0932], [1.0941, 0.3703]]` |
| `labels` | Array | 每筆資料的群編號 | `[1, …]`（共 300 筆） |
| `cluster_sizes` | Array | 各群筆數 | `[73, 116, 111]` |
| `clusters` | Array | 各群的筆數、佔比與中心 | `[{"cluster": 0, "size": 73, "share": 0.2433, "within_sse": 16…, …]`（共 3 筆） |
| `sse` | Float | 群內平方和 SSE | `86.5717` |
| `sse_k1` | Float | K=1 時的 SSE（總變異） | `598.0` |
| `variance_explained` | Float | 變異解釋率 1 − SSE / SSE(K=1) | `0.8552` |
| `silhouette` | Float | 平均輪廓係數（≥ 0.5 合理） | `0.6887` |
| `n_iter` | Integer | Lloyd 迭代次數 | `6` |
| `converged` | Boolean | 是否收斂 | `true` |
| `n_points` | Integer | 資料筆數 | `300` |
| `dimension` | Integer | 特徵維度 | `2` |
| `n_init` | Integer | k-means++ 起點組數 | `10` |
| `seed` | Integer | 亂數種子 | `42` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `分成 3 群，群大小 [73, 116, 111]，SSE=86.57，解釋了 85.5% 的總變異，輪廓係數 0.69。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 沒有真實製程資料時用模擬資料（seed=8，300 筆）。
2. K-Means 假設群接近球形、大小相近，且對離群點敏感。
3. Skill 用樣本標準差標準化（講義用母體），所以 K=1 的 SSE 是 598 而不是 600。
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
| 專案內模組 | — | 本專案 | `_common`, `_kmeans`, `_spc_data` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `kmeans.py run`（講義第 7 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| k＝3 的 SSE（以 Skill 中心為起點重跑） | 86.571656 | 86.571656 | 一致 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入資料與群數 K 防呆 | 資料 300 筆 × 2 維，K=3（允許 1–10）。各欄平均≈0、標準差≈1，符合 z 分數。 | Boundary & Type Validation | math |
| 2 | k-means++ 初始化（多起點） | 以 k-means++ 選初始中心（第一個隨機，其餘依到最近中心距離² 的機率抽取），重複 10 次起點（固定 seed=42）後取 SSE 最小者，避免落入壞的局部解。 | k-means++ Initialization (multi-start) | random |
| 3 | Lloyd 迭代：指派與更新群中心 | Lloyd 迭代：把每個點歸到最近的中心（歐氏距離），再以 μ_k = 群內平均更新中心，直到指派不再改變（最佳起點 6 輪收斂；上限 100 輪）。10 個起點全部在上限內收斂。 | K-Means (Assign to nearest μ_k, update μ_k = mean(S_k)) | Python Built-in |
| 4 | SSE、群大小與輪廓係數評估 | SSE = 86.57（K=1 時為 598.00，變異解釋率 85.5%）；群大小 群0:73、群1:116、群2:111；平均輪廓係數 0.689。 | SSE & Silhouette Evaluation | math |
| 5 | 分群品質 Guardrail 檢核 | 防呆檢核狀態：PASSED（已收斂、無空群）。各群大小皆 ≥3%、輪廓係數 ≥0.5。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
# ... 代表網頁 API 傳入的大型資料（矩陣、前一個 Skill 的結果），由該頁 API 從模擬資料或前一步產生
from skill_20_process_parameter_kmeans import run_kmeans
result = run_kmeans(z_scores=..., k=3)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 分成 3 群，群大小 [73, 116, 111]，SSE=86.57，解釋了 85.5% 的總變異，輪廓係數 0.69。

完整結果 JSON：`results/skill_20_process_parameter_kmeans_result.json`（2026-11-16 執行）。
