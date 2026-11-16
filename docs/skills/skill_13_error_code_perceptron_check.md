# SKILL: skill_13_error_code_perceptron_check

**name**: `skill_13_error_code_perceptron_check`  
**description**: 維修紀錄即時合規判斷：以單層感知器依電流與壓力判斷紀錄是否合規，人工確認與預測不符時更新權重。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-08 |
| 網頁 | 09 維修登錄驗證 |
| 演算法 | 單層感知器（Perceptron） |
| 講義週次 | 第 7 週 |
| 呼叫順序 | 09 頁：skill_12 → skill_13 |
| 程式檔 | `skills/skill_13_error_code_perceptron_check.py` |
| 主函式 | `check_error_code_perceptron()` |
| MCP 工具名 | `skill_13_error_code_perceptron_check` |

---

## 1. 做什麼

**使用者**：設備維修工程師

特徵以訓練集平均與標準差標準化後，計算 f(x) = step(wᵀz + b)，0 = 合規、1 = 異常。若使用者提供人工確認結果且與預測不符，就做一次錯誤驅動更新 w ← w + η(y − ŷ)z，權重狀態存在 `data/perceptron_state.json`；沒有確認結果時不學習。

**程式內的演算法流程**：輸入防呆 -> 載入（或訓練）感知器狀態 -> Guardrail 前置評估 -> 線性超平面劃分 f(x)=step(wᵀz+b) -> 錯誤驅動單點權重更新 w ← w + η(y-ŷ)z

---

## 2. 輸入

函式：`check_error_code_perceptron(features=None, confirmed_label=None, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `features` | Array[Float] | 是 | — | `[電流 A, 壓力 MPa]`，通常來自 skill_12 的 normalized_entry |
| `confirmed_label` | Integer | 否 | `None` | 人工確認結果：0 合規、1 異常；提供且與預測不符時更新權重 |
| `output_json_path` | String | 否 | `None` | 結果 JSON 的存檔路徑；未提供時存到 Skill 的預設位置（`data/` 下） |

本次執行（2026-11-16，經網頁 API）實際傳入的參數：

```json
{
  "features": [
    45.2,
    2.1
  ],
  "confirmed_label": null
}
```

---

## 3. 輸出

回傳一個 JSON 物件，必備 `status`、結果欄位與 5 步 `steps`（附件 F-1）。範例值取自本次執行結果。

| 欄位 | 型別 | 說明 | 本次執行的值 |
| :--- | :--- | :--- | :--- |
| `status` | String | 執行狀態：`success`（有執行完成，包含被 Guardrail 擋下的情況）或 `error`（程式例外） | `success` |
| `found` | Boolean | 是否得到可用結果；被 Guardrail 擋下或查無資料時為 `false` | `true` |
| `features` | Array | 輸入特徵 | `[45.2, 2.1]` |
| `feature_names` | Array | 特徵的程式名稱，順序與輸入向量相同 | `["current_a", "pressure_mpa"]` |
| `validation_result` | Integer | 判定：0 合規、1 異常 | `0` |
| `status_label` | String | `COMPLIANT` / `NON_COMPLIANT` | `COMPLIANT` |
| `decision_score` | Float | 線性分數 wᵀz + b（> 0 判異常） | `-0.1385` |
| `distance_to_hyperplane` | Float | 到決策邊界的帶號距離（越接近 0 越不確定） | `-0.4984` |
| `z_scores` | Array | 標準化後的特徵 | `[-0.3783, 0.0993]` |
| `confirmed_label` | null | 人工確認結果（未提供為 null） | `null` |
| `weight_updated` | Boolean | 本次是否更新了權重 | `false` |
| `update_note` | String | 權重更新說明 | `未提供人工確認結果，不更新權重。` |
| `weights_before` | Object | 更新前權重（w1、w2、bias） | `{"w1": 0.1611, "w2": 0.2263, "bias": -0.1}` |
| `updated_weights` | Object | 更新後權重 | `{"w1": 0.1611, "w2": 0.2263, "bias": -0.1}` |
| `result_after_update` | Integer | 以更新後權重重新判定的結果 | `0` |
| `eta` | Float | 學習率 η | `0.1` |
| `n_updates` | Integer | 累積更新次數 | `0` |
| `update_log` | Array | 權重更新紀錄 | `[]` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo_rule (seed=21，示範規則非真實標準)` |
| `model_metrics` | Object | 模型品質指標（OOB、保留集準確率等） | `{"epochs": 2, "converged": true, "train_mistakes": 5, "n_train": 320, …}` |
| `plot` | Object | 決策邊界散佈圖資料（訓練點與邊界線） | `{"points": [{"x": 22.56, "y": 1.389, "label": 0}, {"x": 64.27, "y": 3.…}` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `[]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `判定為合規（COMPLIANT）：目前電流與壓力的組合落在合規側。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

---

## 4. 限制

1. 專案沒有真實的合規標註資料，目前以示範規則產生的模擬資料（seed=21，400 筆）訓練；規則（高電流且高壓力視為異常）是自訂示範，不是任何真實合規標準。
2. 感知器只能處理線性可分的問題，輸出是硬判定，不是機率。
3. 權重會因人工確認而改變；可呼叫 `reset_perceptron_model()`（09 頁有按鈕）還原。
4. **Guardrail**：輸入不合法或結果不可信時不硬給答案，回 `found: false`、`guardrail_status: BLOCKED_BY_GUARDRAIL (原因)`，`answer_text` 說明原因（`status` 仍為 `success`）；只是需要留意時為 `PASSED_WITH_WARNINGS` 並列在 `warnings`。
5. 只用 Python 標準函式庫，沒有寫死的結果數字；同樣的輸入與資料重跑結果相同（固定亂數種子）。

---

## 5. 套件與授權

| 套件 | 版本 | 授權 | 用途 |
| :--- | :--- | :--- | :--- |
| `csv` | Python 標準函式庫 | PSF License 2.0 | 讀取 CSV |
| `datetime` | Python 標準函式庫 | PSF License 2.0 | 日期處理 |
| `hashlib` | Python 標準函式庫 | PSF License 2.0 | SHA-256 去重 |
| `json` | Python 標準函式庫 | PSF License 2.0 | 讀寫 JSON |
| `math` | Python 標準函式庫 | PSF License 2.0 | 數學函式 |
| `os` | Python 標準函式庫 | PSF License 2.0 | 檔案路徑 |
| `random` | Python 標準函式庫 | PSF License 2.0 | 固定種子的亂數（模擬資料、抽樣） |
| 專案內模組 | — | 本專案 | `_common`, `_repair_data` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `nn.py perceptron`（講義第 7 週）。講義例題資料是圖片，無法重現，對照程式只驗證到本 Skill 的權重與收斂輪數。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| w1 | 0.161098 | 0.161098 | 一致 |  |
| w2 | 0.226347 | 0.226347 | 一致 |  |
| b | -0.1 | -0.1 | 一致 |  |
| 收斂輪數 | 2 | 2 | 一致 |  |
| 訓練時判錯總數 | 5 | 5 | 一致 |  |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 輸入特徵與人工確認結果防呆 | 特徵 [電流 45.2 A, 壓力 2.1 MPa] 為合理範圍內的有限數值；未提供人工確認結果，本次不會更新模型。 | Boundary & Type Validation | math |
| 2 | 載入或訓練感知器狀態 | 載入已存的感知器狀態（資料：synthetic_demo_rule (seed=21，示範規則非真實標準)；學習率 η=0.1）。訓練 320 筆，2 個 epoch 收斂（整輪零錯誤），累計修正 5 次；測試集準確率 100.0%；已累積人工更新 0 次。 | Perceptron Learning Rule (Mistake-driven Training) | csv, json, random |
| 3 | 線性超平面劃分 | z = [-0.378, +0.099]；score = w₁z₁ + w₂z₂ + b = +0.161×-0.378 + +0.226×+0.099 + -0.100 = -0.1385；score > 0 → 0（合規）。距超平面 0.498（z 單位）。 | Linear Hyperplane Classification  f(x)=step(wᵀz+b) | Python Built-in |
| 4 | 錯誤驅動單點權重更新 | 未提供人工確認結果，不更新權重。 | Perceptron Online Update  w ← w + η(y-ŷ)z | Python Built-in |
| 5 | 模型品質與外插 Guardrail 檢核 | 防呆檢核狀態：PASSED（測試集準確率 100.0% ≥ 90%、已收斂、輸入在可判定範圍內）。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_13_error_code_perceptron_check import check_error_code_perceptron
result = check_error_code_perceptron(features=[45.2, 2.1], confirmed_label=None)
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 判定為合規（COMPLIANT）：目前電流與壓力的組合落在合規側。

完整結果 JSON：`results/skill_13_error_code_perceptron_check_result.json`（2026-11-16 執行）。
