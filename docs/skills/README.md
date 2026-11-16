# 29 個 Skill 說明文件（SKILL.md）

依說明文件附件 F-1 格式產生：name、description，再依序是做什麼、輸入、輸出、限制、套件與授權、對答案紀錄、步驟，另附執行範例。產生日期：2026-11-16。

## 怎麼放進專案

1. 把 `docs/skills/` 底下 29 個 .md 複製到專案的 `docs/skills/`（skill_01、skill_02 會覆蓋舊版）。
2. `results/` 是這次執行的完整結果 JSON，可當作附件 D-3「結果檔：都有結果與 5 步 steps」的佐證；不需要放進 `docs/`。
3. 不要把這些檔案放在 `docs/` 根目錄：skill_01 會掃描根目錄的文件來回答問題，放進去會干擾法規檢索。

## 內容怎麼來的

- **輸入、輸出、步驟、套件**：從程式碼讀出參數與 import，並實際執行每個 Skill 取得輸出欄位與 5 步 steps，表格中的數字都是執行結果，沒有手填。
- **執行輸入**：採用附件 B-1 驗收條件與 13 頁截圖的示範輸入；08、09、12、13 頁的 Skill 透過網頁 API 呼叫取得（與網頁畫面一致），其餘直接呼叫。
- **對答案紀錄**：執行 `python tools/skill_vs_course.py`，43 個比對項目都放進對應 Skill 的第 6 節。
- **做什麼、限制、參數說明**：依程式內的說明文字與附件 A、B 撰寫。

## 請你複核的地方

- 第 1 節的使用者與業務情境、第 4 節的限制寫法是否符合你的報告用語。
- skill_01、02、10 的手算紀錄標為【待補】（附件 D-3 要求餘弦、Jaccard 以 3–5 筆小資料手算）。
- 舊版 skill_01 說明寫門檻預設 0.25，程式實際是 0.10，新版已改為與程式一致。
- skill_25 預設自動門檻切成 2 個階層；13 頁截圖的設定是 3 個階層，引用數字時請註明門檻。

## 執行環境說明

GitHub 上的 repo 缺少 234 個法規條文檔，這次先用 `tools/split_laws.py` 從 `docs/specs/` 的兩份 PDF 重新產生（與 `data/catalog_manifest.json` 完全一致）才能執行 skill_01、26、29。另外，repo 根目錄有一份和 `skills/` 重複的 `_*.py`，會讓 `app.py` 把專案根目錄判斷成上一層資料夾（skill_29 讀不到題庫、skill_27 找不到上傳檔），這次執行時已移除這些重複檔。

## 29 個 Skill 一覽

| # | Skill | 類別 | 故事 | 演算法 | 本次執行的 Guardrail |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 01 | [`skill_01_tool_regulation_search`](docs/skills/skill_01_tool_regulation_search.md) | 檢索 | US-01、US-16 | KNN + 餘弦相似度（TF-IDF） | `None` |
| 02 | [`skill_02_machine_qualification_match`](docs/skills/skill_02_machine_qualification_match.md) | 檢索 | US-02 | KNN + Jaccard 集合相似度 | `PASSED (Score 0.5000 >= Threshold 0.2)` |
| 03 | [`skill_03_sensor_data_preprocessing`](docs/skills/skill_03_sensor_data_preprocessing.md) | 整理 | US-03、US-18 | Z-Score 標準化 | `PASSED` |
| 04 | [`skill_04_equipment_rul_prediction`](docs/skills/skill_04_equipment_rul_prediction.md) | 分析 | US-03 | 多元線性迴歸（OLS） | `PASSED` |
| 05 | [`skill_05_degradation_feature_attribution`](docs/skills/skill_05_degradation_feature_attribution.md) | 分析 | US-03 | OLS 係數貢獻度拆解 | `PASSED (R² 0.995 >= 0.5)` |
| 06 | [`skill_06_failure_probability_calc`](docs/skills/skill_06_failure_probability_calc.md) | 分析 | US-04 | 邏輯迴歸（Sigmoid） | `PASSED` |
| 07 | [`skill_07_risk_level_classification`](docs/skills/skill_07_risk_level_classification.md) | 分析 | US-04 | 勝算比 + 燈號劃分（邏輯迴歸延伸） | `PASSED` |
| 08 | [`skill_08_cost_sensitive_threshold_tuning`](docs/skills/skill_08_cost_sensitive_threshold_tuning.md) | 分析 | US-05 | 門檻成本取捨 | `PASSED` |
| 09 | [`skill_09_similar_repair_case_search`](docs/skills/skill_09_similar_repair_case_search.md) | 分析 | US-06 | KNN（加權歐氏距離） | `PASSED (Best 1.0000 >= 0.3)` |
| 10 | [`skill_10_error_code_feature_matching`](docs/skills/skill_10_error_code_feature_matching.md) | 整理 | US-06 | 故障碼對照 + 特徵標準化加權（逆變異數權重、高斯核親和度） | `PASSED` |
| 11 | [`skill_11_spare_parts_recommendation`](docs/skills/skill_11_spare_parts_recommendation.md) | 分析 | US-07 | 物品協同過濾（Item-based CF） | `PASSED_WITH_WARNINGS` |
| 12 | [`skill_12_repair_log_entry_validation`](docs/skills/skill_12_repair_log_entry_validation.md) | 整理 | US-08 | 正則表達式 + 臨界值檢查 | `PASSED` |
| 13 | [`skill_13_error_code_perceptron_check`](docs/skills/skill_13_error_code_perceptron_check.md) | 分析 | US-08 | 單層感知器（Perceptron） | `PASSED` |
| 14 | [`skill_14_yield_rate_anomaly_detection`](docs/skills/skill_14_yield_rate_anomaly_detection.md) | 分析 | US-09 | 隨機森林 | `PASSED` |
| 15 | [`skill_15_feature_importance_ranking`](docs/skills/skill_15_feature_importance_ranking.md) | 分析 | US-09 | 隨機森林 MDI（吉尼重要度） | `PASSED` |
| 16 | [`skill_16_root_cause_attribution_report`](docs/skills/skill_16_root_cause_attribution_report.md) | 分析 | US-09 | 結果整合報告（啟發式歸因） | `PASSED_WITH_WARNINGS` |
| 17 | [`skill_17_steel_surface_defect_classify`](docs/skills/skill_17_steel_surface_defect_classify.md) | 分析 | US-10 | CART 決策樹 | `PASSED` |
| 18 | [`skill_18_defect_geometric_feature_eval`](docs/skills/skill_18_defect_geometric_feature_eval.md) | 分析 | US-10 | 決策樹吉尼重要度 | `PASSED_WITH_WARNINGS` |
| 19 | [`skill_19_decision_tree_rule_extraction`](docs/skills/skill_19_decision_tree_rule_extraction.md) | 分析 | US-11 | 代價複雜度剪枝 + IF-THEN 規則 | `PASSED_WITH_WARNINGS` |
| 20 | [`skill_20_process_parameter_kmeans`](docs/skills/skill_20_process_parameter_kmeans.md) | 分析 | US-12 | K 平均分群 | `PASSED` |
| 21 | [`skill_21_elbow_method_optimal_k`](docs/skills/skill_21_elbow_method_optimal_k.md) | 分析 | US-12 | 手肘法（SSE） | `PASSED` |
| 22 | [`skill_22_spc_control_limit_monitoring`](docs/skills/skill_22_spc_control_limit_monitoring.md) | 分析 | US-13 | SPC（Mean ± 3σ） | `PASSED_WITH_WARNINGS` |
| 23 | [`skill_23_ipi_mlp_forecast`](docs/skills/skill_23_ipi_mlp_forecast.md) | 分析 | US-14 | 多層類神經網路（MLP，真實訓練） | `PASSED_WITH_WARNINGS` |
| 24 | [`skill_24_preventive_maintenance_hierarchy`](docs/skills/skill_24_preventive_maintenance_hierarchy.md) | 分析 | US-15 | 凝聚階層式分群 | `PASSED` |
| 25 | [`skill_25_factory_risk_dendrogram_eval`](docs/skills/skill_25_factory_risk_dendrogram_eval.md) | 分析 | US-15 | Dendrogram 切割與評估 | `PASSED_WITH_WARNINGS` |
| 26 | [`skill_26_document_catalog_query`](docs/skills/skill_26_document_catalog_query.md) | 檢索 | US-17 | SQLite 元資料過濾 | `PASSED` |
| 27 | [`skill_27_kb_import_pipeline`](docs/skills/skill_27_kb_import_pipeline.md) | 匯入 | US-18 | 正則清洗 + SHA-256 去重 + 滑動視窗切片 | `PASSED_WITH_WARNINGS` |
| 28 | [`skill_28_data_freshness_check`](docs/skills/skill_28_data_freshness_check.md) | 維運與評估 | US-19 | 落後月數 + 時間指數衰減 | `PASSED_WITH_WARNINGS` |
| 29 | [`skill_29_retrieval_quality_eval`](docs/skills/skill_29_retrieval_quality_eval.md) | 維運與評估 | US-19 | Hit@3、MRR | `PASSED` |

## 程式改了以後怎麼重新產生

`_generator/` 是產生這些文件的腳本，只用標準函式庫（run_api.py 需要 Flask）。在專案資料夾外執行：

```bash
python _generator/run_all.py <專案資料夾> <暫存資料夾>       # 直接執行 29 個 Skill
python _generator/run_api.py <專案資料夾> <暫存資料夾>       # 用網頁 API 執行 08、09、12、13 頁
cd <專案資料夾> && python tools/skill_vs_course.py > <暫存資料夾>/skill_vs_course.txt
python _generator/gen_skill_md.py <專案資料夾> <暫存資料夾> <輸出資料夾>
```

人工撰寫的說明（業務情境、參數說明、限制）都在 `_generator/meta.py`，改那裡再重跑即可。執行前 `docs/` 要有 234 個法規條文檔，根目錄不能有重複的 `_*.py`。
