# SKILL: skill_08_cost_sensitive_threshold_tuning

**name**: `skill_08_cost_sensitive_threshold_tuning`  
**description**: 代價敏感預警門檻：掃描 0–1 的門檻，找出「停機損失 × 漏報 + 檢修成本 × 誤報」總成本最低的預警門檻。

| 項目 | 內容 |
| :--- | :--- |
| 類別 | 分析 |
| 對應故事 | US-05 |
| 網頁 | 07 故障風險評估 |
| 演算法 | 門檻成本取捨 |
| 講義週次 | 第 5 週（延伸） |
| 呼叫順序 | 07 頁：skill_06 → skill_07 → skill_08 |
| 程式檔 | `skills/skill_08_cost_sensitive_threshold_tuning.py` |
| 主函式 | `tune_cost_threshold()` |
| MCP 工具名 | `skill_08_cost_sensitive_threshold_tuning` |

---

## 1. 做什麼

**使用者**：設備維修工程師、維修主管

用 skill_06 模型在測試集的預測機率，對每個門檻 θ 統計漏報 FN（實際故障卻沒預警，付停機損失）與誤報 FP（實際正常卻預警，付檢修成本），計算 Cost(θ) = C_down·FN + C_inspect·FP，取最小者為最佳門檻，並與「預設 0.5」「完全不預警」「全部派工」三種基準比較。若有提供本次故障機率，會直接給出派工與否的決策。

**程式內的演算法流程**：成本矩陣防呆 -> 載入測試集預測機率 -> 掃描門檻 θ∈[0,1] 統計 FN/FP -> 極小化 Cost(θ)=C_down·FN(θ)+C_inspect·FP(θ) -> 基準比較 Guardrail

---

## 2. 輸入

函式：`tune_cost_threshold(cost_downtime=50000, cost_inspection=2000, failure_probability=None, step=0.01, output_json_path=None)`

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `cost_downtime` | Float | 否 | `50000` | 漏報一次的停機損失（元） |
| `cost_inspection` | Float | 否 | `2000` | 誤報一次的檢修成本（元） |
| `failure_probability` | Float | 否 | `None` | 本次設備的故障機率；有提供時會輸出 `decision` |
| `step` | Float | 否 | `0.01` | 門檻掃描間距 |
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
| `cost_downtime` | Float | 停機損失設定 | `50000.0` |
| `cost_inspection` | Float | 誤報成本設定 | `2000.0` |
| `data_source` | String | 本次使用的資料來源；`synthetic_demo (seed=…)` 表示程式內建的模擬資料 | `synthetic_demo (seed=42)` |
| `optimal_threshold` | Float | 最佳門檻 | `0.04` |
| `optimal_threshold_range` | Array | 總成本同為最低的門檻區間 | `[0.04, 0.04]` |
| `total_cost_min` | Float | 測試集最低總成本 | `182000.0` |
| `cost_per_equipment` | Float | 平均每台成本 | `910.0` |
| `n_eval` | Integer | 評估筆數（測試集） | `200` |
| `n_eval_failures` | Integer | 其中實際故障筆數 | `66` |
| `theoretical_threshold` | Float | 理論門檻 C_inspect / (C_inspect + C_down) | `0.0385` |
| `cost_ratio` | Float | 成本比 | `25.0` |
| `optimal_confusion` | Object | 最佳門檻下的 TP / FP / FN / TN | `{"tp": 66, "fp": 91, "fn": 0, "tn": 43}` |
| `baselines` | Array | 與預設 0.5、完全不預警、全部派工的成本比較 | `[{"name": "最佳門檻", "threshold": 0.04, "total_cost": 182000.0, …, …]`（共 4 筆） |
| `saving_vs_best_trivial` | Float | 比最好的簡單策略省下多少 | `86000.0` |
| `threshold_curve` | Array | 每個門檻的 FN、FP 與總成本（畫成本曲線用） | `[{"threshold": 0.0, "fn": 0, "fp": 134, "tp": 66, "tn": 0, "d…, …]`（共 101 筆） |
| `decision` | null | 本次設備是否派工（未提供 failure_probability 時為 null） | `null` |
| `warnings` | Array | 非致命的提醒（例如外插、資料為模擬、樣本太少），網頁以黃色提示顯示 | `["最佳門檻是在同一測試集上挑選，最低成本略為樂觀；正式使用請另備驗證資料。"]` |
| `guardrail_status` | String | 防呆檢核結果：`PASSED`、`PASSED_WITH_WARNINGS` 或 `BLOCKED_BY_GUARDRAIL (原因)` | `PASSED` |
| `answer_text` | String | 給使用者看的一段結論文字（網頁結果卡與 MCP 工具回覆都用這一段） | `在停機損失 50,000、誤報檢修 2,000 的成本下，最佳預警門檻為 0.04，測試集最低總成本 182,000（平均每台 910）。` |
| `steps` | Array | 5 步推導日誌，供網頁「這個結果怎麼算的」面板顯示（見第 7 節） | 見第 7 節 |

> **與規格書 `29_skill.md` 的差異**：規格書範例輸出 `fp`、`fn`，程式放在 `optimal_confusion` 物件內。


---

## 4. 限制

1. 門檻在同一份測試集上挑選，最低成本略為樂觀；正式使用應另備驗證資料。
2. 成本只算誤報的檢修費；講義的定義是每一張警示（含真的會壞的）都算檢修費，兩者最佳門檻相同（0.04），但總成本不同（182,000 vs. 314,000）。
3. 成本數字是使用者輸入的假設值。
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
| `statistics` | Python 標準函式庫 | PSF License 2.0 | 平均數、標準差 |
| 專案內模組 | — | 本專案 | `_common`, `_failure_model`, `skill_03_sensor_data_preprocessing`, `skill_04_equipment_rul_prediction` |

無第三方套件，不需 `pip install`。開發環境為 Python 3.14，本文件的執行結果以 Python 3.13 產生，兩者結果相同。不使用任何外部模型或 API。

---

## 6. 對答案紀錄

對照 `logit.py cost`（講義第 5 週）。課堂工具沒有提供給學生，改用 `tools/course_ref.py`：依講義公式、只用標準函式庫自行實作的對照程式（先重現講義例題 63 項全部一致，見附件 F-3）。

指令（在專案根目錄）：`python tools/skill_vs_course.py`　執行日期：2026-11-16

| 項目 | Skill | 對照程式 | 結果 | 說明 |
| :--- | :--- | :--- | :---: | :--- |
| 最佳門檻（Skill 的成本定義重算） | 0.04 | 0.04 | 一致 |  |
| 最低總成本（Skill 的成本定義重算） | 182000.0 | 182000.0 | 一致 |  |
| 最佳門檻（講義的成本定義） | 0.04 | 0.04 | 一致 | 講義把每一張警示（含真的會壞的 TP）都算檢修費；Skill 只算誤報（FP）的檢修費 |
| 最低總成本（講義的成本定義） | 182000.0 | 314000.0 | 有差異 | 同上：定義不同，總成本不能直接比 |

---

## 7. 步驟

以下為本次執行實際輸出的 5 步 `steps`（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）。

| # | 步驟 | 本次執行的說明 | 演算法 | 套件 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 成本矩陣與掃描參數防呆 | 成本矩陣：停機損失 C_down=50,000、誤報檢修 C_inspect=2,000，成本比 25.0:1；掃描間距 0.01。 | Boundary & Type Validation | math |
| 2 | 載入測試集預測機率與真實標籤 | 自 synthetic_demo (seed=42) 取得測試集 200 筆預測機率（故障 66 / 正常 134），皆為模型未見過的資料；測試集 AUC=0.894。 | Out-of-sample Probability Evaluation | skill_06 模型 (純標準庫) |
| 3 | 掃描門檻並統計 FN / FP | 掃描 101 個門檻 θ ∈ [0, 1]；每個 θ 以「p ≥ θ 即預警」統計 FN（漏報）與 FP（誤報）。θ=0 時全數預警（FP=134），θ=1 時全不預警（FN=66）。 | Threshold Sweep & Confusion Counting | Python Built-in |
| 4 | 極小化預期總成本求最佳門檻 | Cost(θ)=C_down·FN+C_inspect·FP 的最小值為 182,000，出現於 θ ∈ [0.04, 0.04]（共 1 個等價門檻）；取中位數 θ*=0.04（FN=0、FP=91）。 | Cost-sensitive Tuning  min C_down·FN + C_inspect·FP | Python Built-in |
| 5 | 基準比較 Guardrail 檢核與決策建議 | 防呆檢核狀態：PASSED。對照：0.5 門檻成本 1,226,000、完全不預警 3,300,000、全部檢修 268,000；成本取捨的理論門檻 0.038。 | Threshold-based Guardrail Evaluation | Python Control Flow |

---

## 8. 執行範例

```python
# 在專案根目錄執行
import sys; sys.path.append("skills")
from skill_08_cost_sensitive_threshold_tuning import tune_cost_threshold
result = tune_cost_threshold()
print(result["answer_text"])
```

本次結果（`guardrail_status`：`PASSED`）：

> 在停機損失 50,000、誤報檢修 2,000 的成本下，最佳預警門檻為 0.04，測試集最低總成本 182,000（平均每台 910）。

完整結果 JSON：`results/skill_08_cost_sensitive_threshold_tuning_result.json`（2026-11-16 執行）。
