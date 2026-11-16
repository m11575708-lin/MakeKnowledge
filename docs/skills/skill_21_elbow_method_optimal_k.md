# SKILL: skill_21_elbow_method_optimal_k

**name**: `skill_21_elbow_method_optimal_k`  
**description**: 手肘法決定群數：對 K = 1…max_k 計算最小 SSE，以弦距法找出 SSE 下降明顯變緩的轉折點，並用輪廓係數交叉檢查。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-12 |
| 網頁 | 12 製程分群與 SPC |
| 演算法 | 手肘法（SSE） |
| 講義週次 | 第 7 週 |
| 呼叫順序 | 12 頁：skill_21 → skill_20 → skill_22 |
| 程式檔 | `skills/skill_21_elbow_method_optimal_k.py` |
| 主函式 | `find_optimal_k()` |
| MCP 工具名 | `skill_21_elbow_method_optimal_k` |

---

## 1. 做什麼

**使用者**：品質與製程工程師

每個 K 用多組 k-means++ 起點取最小 SSE，畫出 SSE–K 曲線；以弦距法（各點到首尾連線的距離）量化手肘位置並給出手肘強度。另外計算輪廓係數，兩種方法建議的 K 不同時警告。

**程式內的演算法流程**：輸入防呆 -> 逐一 K=1..max_k 以多組 k-means++ 起點取最小 SSE -> 弦距法找手肘 -> 輪廓係數交叉檢查 -> Guardrail

---

## 2. 輸入

函式：`find_optimal_k(data=None, max_k=8, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `data` | Array[Array[Float]] | 是 | — | n × d 的 z 分數矩陣 |
| `max_k` | Integer | 否 | `8` | 最多試到幾群 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "data": "<300x2 陣列>",
  "max_k": 8
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `optimal_k` | Integer | 建議群數 | `3` |
| `sse` | Float | 建議 K 的 SSE | `86.5717` |
| `sse_by_k` | Array | K = 1…max_k 的最小 SSE（畫手肘圖用） | `[598.0, …]`（共 8 筆） |
| `k_values` | Array | 試過的 K | `[1, 2, 3, 4, 5, 6, 7, 8]` |
| `elbow_strength` | Float | 手肘強度（弦距法最大距離，0–1） | `0.6393` |
| `elbow_distances` | Array | 各 K 到首尾連線的距離 | `[0.0, 0.3906, 0.6393, 0.5194, 0.3941, 0.265, 0.1342, 0.0]` |
| `silhouette_by_k` | Object | 各 K 的平均輪廓係數 | `{"2": 0.5395, "3": 0.6887, "4": 0.5527, "5": 0.4253, "6": 0.4295, "7":…}` |
| `silhouette_best_k` | Integer | 輪廓係數最高的 K | `3` |
| `n_points` | Integer | 資料筆數 | `300` |
| `n_init` | Integer | 每個 K 的起點組數 | `10` |
| `seed` | Integer | 亂數種子 | `42` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `手肘法建議分成 K=3 群（SSE=86.57，手肘強度 0.64）；輪廓係數同樣支持 K=3。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 手肘強度只描述曲線彎曲程度，不能證明資料真的有群結構（沒有群結構的資料手肘強度也可能約 0.4）；要看輪廓係數（≥ 0.5 才算合理）。
2. 資料沒有群結構時 SSE 曲線近似直線，optimal_k 不可信，會警告。
3. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
4. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

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

對照 `kmeans.py elbow`（講義第 7 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| k＝3 的最小 SSE（對照試 200 組起點） | 86.571656 | 86.571656 | 一致 | K 平均只保證局部最小；兩邊一樣表示 Skill 的 10 組起點已找到同一個最小值 |
| k＝1 的 SSE | 598.0 | 598.0 | 一致 | Skill 用樣本標準差（÷ n−1），所以 k＝1 是 2×(n−1)＝598；講義用母體標準差會是 2n＝600 |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入資料與 max_k 防呆 | 資料 300 筆 × 2 維，皆為有限數值；比較 K=1..8。各欄平均≈0、標準差≈1，符合 z 分數。 | Boundary & Type Validation | math |
| 2 | 逐一 K 以多組起點計算最小 SSE | 每個 K 以 k-means++ 初始化重複 10 次（固定 seed=42）取 SSE 最小者；SSE = Σ\|\|x-μ_k\|\|²。結果：K=1: 598.00、K=2: 303.05、K=3: 86.57、K=4: 73.89、K=5: 64.16、K=6: 56.57、K=7: 49.90、K=8: 45.13。SSE 單調下降：是。 | K-Means (k-means++ init, multi-start) SSE per K | random, math |
| 3 | 弦距法判定手肘轉折點 | 把 (K, SSE) 正規化到 [0,1]，計算各點到「K=1 與 K=8 連線」的距離，距離最大處為手肘：K=3（手肘強度 0.64，0 代表直線、越大轉折越明顯）。K=3 的 SSE=86.57，相當於 K=1 時的 14.5%。 | Elbow Method (max distance to chord) | Python Built-in |
| 4 | 輪廓係數交叉檢查 | 平均輪廓係數（-1~1，越大群越分明）：K=2: 0.539、K=3: 0.689、K=4: 0.553、K=5: 0.425、K=6: 0.430、K=7: 0.345、K=8: 0.326。輪廓係數最高的是 K=3（0.689）。 | Silhouette Score Cross-check | random, math |
| 5 | 轉折可信度 Guardrail 檢核 | 防呆檢核狀態：PASSED。手肘強度 0.64 ≥ 0.15、最高輪廓係數 ≥ 0.5、兩種方法給出相同的 K、資料已標準化。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
# ... 代表網頁 API 傳入的大型資料（矩陣、前一個 Skill 的結果），由該頁 API 從模擬資料或前一步產生
from skill_21_elbow_method_optimal_k import find_optimal_k
result = find_optimal_k(data=..., max_k=8)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 手肘法建議分成 K=3 群（SSE=86.57，手肘強度 0.64）；輪廓係數同樣支持 K=3。

完整結果 JSON：`results/skill_21_elbow_method_optimal_k_result.json`（2026-11-16 執行）。
