# SKILL: skill_23_ipi_mlp_forecast

**name**: `skill_23_ipi_mlp_forecast`  
**description**: 工業生產指數預測：真實訓練單隱藏層 MLP（反向傳播），預測未來三個月的 IPI，並與「延續上月」基準比較。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-14 |
| 網頁 | 13 生產指數與維護 |
| 演算法 | 多層類神經網路（MLP，真實訓練） |
| 講義週次 | 第 7 週 |
| 呼叫順序 | 13 頁：skill_23（與 skill_24 → 25 並列） |
| 程式檔 | `skills/skill_23_ipi_mlp_forecast.py` |
| 主函式 | `forecast_ipi_mlp()` |
| MCP 工具名 | `skill_23_ipi_mlp_forecast` |

---

## 1. 做什麼

**使用者**：生產排程主管 / 廠長（規劃下季產能）

對未來第 1、2、3 個月各訓練一個網路（直接多步預測），預測變化量 IPI(t+h) − IPI(t)；網路為 tanh 隱藏層、線性輸出、MSE 損失，以全批次梯度下降與鏈鎖律反向傳播更新 Δw = −η(∂L/∂w + λw)。依時間切分前 80% 訓練、後 20% 測試，並剔除目標落在測試期的訓練樣本避免資訊洩漏。測試 RMSE 與「延續上月」基準比較，沒勝過就明說。

**程式內的演算法流程**：輸入驗證與特徵建構 -> 時間切分與標準化 -> 前向傳播 -> 反向傳播訓練（梯度下降） -> 測試期誤差對照「延續上月」基準 + Guardrail

---

## 2. 輸入

函式：`forecast_ipi_mlp(historical_ipi=None, export_orders=None, utilization=None, start_month=None, features=None, epochs=500, learning_rate=0.05, hidden_units=6, seed=42, weight_decay=0.001, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `historical_ipi` | Array[Float] | 否 | `None` | 月度 IPI 序列；未提供時用模擬資料 |
| `export_orders` | Array[Float] | 否 | `None` | 月度出口訂單（與 IPI 等長） |
| `utilization` | Array[Float] | 否 | `None` | 月度稼動率（與 IPI 等長） |
| `start_month` | String | 否 | `None` | 第一筆資料的月份（`YYYY-MM`），用於季節變數 |
| `features` | Array[String] | 否 | `None` | 要使用的特徵名稱 |
| `epochs` | Integer | 否 | `500` | 訓練輪數 |
| `learning_rate` | Float | 否 | `0.05` | 學習率 η |
| `hidden_units` | Integer | 否 | `6` | 隱藏單元數 |
| `seed` | Integer | 否 | `42` | 初始權重亂數種子 |
| `weight_decay` | Float | 否 | `0.001` | L2 權重衰減 λ |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "features": [
    "ipi",
    "export",
    "util",
    "season"
  ],
  "epochs": 500,
  "learning_rate": 0.05,
  "hidden_units": 6
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `ipi_forecast_next_quarter` | Array | 未來三個月 IPI 預測 | `[127.078, 125.815, 126.221]` |
| `forecast_interval` | Array | 各月粗略區間（預測 ± 1.96 × 測試 RMSE） | `[[124.809, 129.346], [119.955, 131.675], [118.556, 133.886]]` |
| `training_loss_final` | Float | 第 1 個月網路的最終訓練損失 | `0.18559` |
| `training_loss_final_all` | Object | 三個網路各自的最終訓練損失 | `{"1": 0.18559, "2": 0.32001, "3": 0.43615}` |
| `loss_history` | Array | 第 1 個月網路的損失曲線 | `[[0, 1.068416], …]`（共 200 筆） |
| `loss_history_all` | Object | 三個網路的損失曲線 | `{"1": [[0, 1.068416], [3, 0.843086], [5, 0.747124], [8, 0.644616], [10…}` |
| `convergence_epoch` | null | 損失收斂的輪數（未判定收斂時為 null） | `null` |
| `test_rmse` | Float | 測試期 RMSE（三個月平均） | `2.8831` |
| `baseline_rmse` | Float | 「延續上月」基準的 RMSE | `3.527` |
| `beats_baseline` | Boolean | 是否勝過基準 | `true` |
| `improvement_pct` | Float | 相對基準的改善百分比 | `18.3` |
| `horizons` | Array | 第 1、2、3 個月各自的訓練／測試 RMSE 與基準 | `[{"h": 1, "train_rmse": 1.0837, "train_baseline_rmse": 2.5239…, …]`（共 3 筆） |
| `test_predictions_h1` | Array | 測試期逐月的實際值、預測值與基準 | `[{"t": 97, "actual": 121.33, "predicted": 121.231, "baseline"…, …]`（共 23 筆） |
| `split_index` | Integer | 訓練／測試切分點 | `96` |
| `n_months` | Integer | 資料月數 | `120` |
| `last_ipi` | Float | 最新一期 IPI | `124.3` |
| `features` | Array | 本次輸入的特徵值 | `["ipi", "export", "util", "season"]` |
| `feature_names` | Array | 特徵的程式名稱，順序與輸入向量相同 | `["IPI 1月變化", …]`（共 10 筆） |
| `hyperparameters` | Object | 實際使用的超參數 | `{"epochs": 500, "learning_rate": 0.05, "hidden_units": 6, "weight_deca…}` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=13，示範資料非真實統計)` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["預測期越遠，相對基準的改善越小，第 3 個月的預測不確定性明顯較高", …]`（共 3 筆） |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED_WITH_WARNINGS` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `未來三個月 IPI 預估 127.1、125.8、126.2（現值 124.3）；測試期 RMSE 2.883，勝過「延續上月」基準 3.5…` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |
| `disclaimer` | String | 「僅供參考」聲明 | `預測結果僅供參考，不應作為生產排程或投資的唯一依據` |

---

## 4. 限制

1. 沒有真實 CSV 時用模擬資料（seed=13，120 個月）。
2. 區間是粗略的經驗區間，不是嚴格的信賴區間；輸出一律標示「僅供參考」。
3. 網路結構（tanh、線性輸出、MSE）與講義例題不同，無法直接套講義例題；以數值微分驗證梯度。
4. 執行約 3 秒（三個網路各 500 輪，另以全部資料重訓一次）。
5. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
6. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| 專案內模組 | — | 本專案 | `_common`, `_ipi_data`, `_mlp` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `nn.py backprop`（講義第 7 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| ∂L/∂W1[0][0] 解析 vs 數值微分 | 0.013818 | 0.013818 | 一致 | 講義的盆栽網路用 sigmoid 輸出與 ½(ŷ−y)²；Skill 是 tanh 隱藏層、線性輸出、MSE（預測數值用），所以改用數值微分驗證鏈鎖律 |
| ∂L/∂W2[2] 解析 vs 數值微分 | -0.02132 | -0.02132 | 一致 |  |
| ∂L/∂b1[1] 解析 vs 數值微分 | 0.135868 | 0.135868 | 一致 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入驗證與特徵建構 | 資料 120 個月（synthetic_demo (seed=13，示範資料非真實統計)），首月為 1 月；使用特徵 10 欄：IPI 1月變化、IPI 3月變化、出口訂單 1月變化、稼動率、目標季=Q2、目標季=Q3、目標季=Q4、當季=Q2、當季=Q3、當季=Q4；對 h = 1、2、3（未來三個月）各建一個樣本集，目標為變化量 IPI(t+h) − IPI(t)。 | Boundary & Type Validation + Feature Engineering (Δ, season dummies) | math |
| 2 | 時間切分與標準化（僅用訓練期統計量） | 以第 96 個月為界做時間切分（前 96 個月為訓練期、後 24 個月為測試期）；h=1 訓練樣本 92、測試樣本 23（目標落在測試期的訓練樣本已剔除）；特徵與目標的平均、標準差只用訓練樣本計算，測試資料不參與。 | Chronological Train/Test Split + Z-Score (train stats only) | math |
| 3 | 前向傳播（tanh 隱藏層） | 網路結構：輸入 10 → 隱藏 6（tanh）→ 輸出 1（線性），每個網路 73 個參數、共 3 個網路；ŷ = Σ W₂ⱼ·tanh(Σ W₁ⱼᵢxᵢ + b₁ⱼ) + b₂。隨機初始權重（seed=42）的訓練 MSE（標準化單位）：h=1: 1.068、h=2: 1.073、h=3: 0.728。 | MLP Forward Propagation  ŷ = W₂·tanh(W₁x + b₁) + b₂ | math |
| 4 | 反向傳播與梯度下降訓練 | 全批次梯度下降 500 個 epoch、學習率 η=0.05、L2 權重衰減 λ=0.001；反向傳播更新 w ← w − η(∂L/∂w + λw)。h=1 的訓練 MSE 由 1.068 降到 0.186（尚未達到收斂判準）。 | Backpropagation (Chain Rule)  Δw = -η ∂L/∂w | random, math |
| 5 | 測試誤差對照基準與 Guardrail 檢核 | 測試期（23 個月）逐期 RMSE：h=1 模型 1.157 vs 基準 2.607；h=2 模型 2.990 vs 基準 3.469；h=3 模型 3.910 vs 基準 4.364；整體 測試期 RMSE 2.883，勝過「延續上月」基準 3.527（改善 18.3%）。以全部資料重訓後預測下一季：[127.078, 125.815, 126.221]。防呆檢核狀態：PASSED_WITH_WARNINGS。預測期越遠，相對基準的改善越小，第 3 個月的預測不確定性明顯較高；訓練損失在最後 50 個 epoch 仍下降超過 1%，可能尚未收斂；可增加 epoch 或學習率（誤差指標以目前訓練結果為準） | RMSE vs Persistence Baseline + Threshold-based Guardrail | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_23_ipi_mlp_forecast import forecast_ipi_mlp
result = forecast_ipi_mlp(features=['ipi', 'export', 'util', 'season'], epochs=500, learning_rate=0.05, hidden_units=6)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED_WITH_WARNINGS`）：

> 未來三個月 IPI 預估 127.1、125.8、126.2（現值 124.3）；測試期 RMSE 2.883，勝過「延續上月」基準 3.527（改善 18.3%）。預測結果僅供參考，不應作為生產排程或投資的唯一依據。

完整結果 JSON：`results/skill_23_ipi_mlp_forecast_result.json`（2026-11-16 執行）。
