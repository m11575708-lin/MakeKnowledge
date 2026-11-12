# 製造業知識庫系統：29 個 Skill 模組彙整對照表（v2 統一版）

> 本檔取代舊版 `25_skill.md`。v2 新增共同網頁用的 Skill 26–29、`skill_23` 更名為 `skill_23_ipi_mlp_forecast`，並修正各 Skill 對應的故事與頁面。
>
> **共同規格**：每個 Skill 回傳的 JSON 都必須有 `status`、結果欄位，以及 5 步 `steps` 陣列（每步含 `step_number`、`step_name`、`description`、`skill_name`、`algorithm_used`、`package_used`）；需要事先算好的結果存成 `data/results/<skill_name>.json`。只用 Python 標準函式庫（AnythingLLM 串接用 `requests`）。JSON 範例中的數字為示意值。

---

## 一、 29 個 Skill 完整清單總覽

| 編號 | Skill 名稱 | 類別 | 故事 | 演算法 / 核心機制 | 頁面 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 01 | `skill_01_tool_regulation_search` | 檢索 | US-01、US-16 | KNN + 餘弦相似度 (TF-IDF) | 01、05 |
| 02 | `skill_02_machine_qualification_match` | 檢索 | US-02 | KNN + Jaccard 集合相似度 | 05 |
| 03 | `skill_03_sensor_data_preprocessing` | 整理 | US-03、US-18 | Z-Score 標準化 | 06（03 匯入時亦呼叫） |
| 04 | `skill_04_equipment_rul_prediction` | 分析 | US-03 | 多元線性迴歸 (OLS) | 06 |
| 05 | `skill_05_degradation_feature_attribution` | 分析 | US-03 | OLS 係數貢獻度拆解 | 06 |
| 06 | `skill_06_failure_probability_calc` | 分析 | US-04 | 邏輯迴歸 (Sigmoid) | 07 |
| 07 | `skill_07_risk_level_classification` | 分析 | US-04 | 勝算比 + 燈號劃分 | 07 |
| 08 | `skill_08_cost_sensitive_threshold_tuning` | 分析 | US-05 | 門檻成本取捨 | 07 |
| 09 | `skill_09_similar_repair_case_search` | 分析 | US-06 | KNN（歐氏距離） | 08 |
| 10 | `skill_10_error_code_feature_matching` | 整理 | US-06 | 故障碼對照 + 特徵標準化加權 | 08 |
| 11 | `skill_11_spare_parts_recommendation` | 分析 | US-07 | 物品協同過濾 (Item-based CF) | 08 |
| 12 | `skill_12_repair_log_entry_validation` | 整理 | US-08 | 正則表達式 + 臨界值檢查 | 09 |
| 13 | `skill_13_error_code_perceptron_check` | 分析 | US-08 | 單層感知器 (Perceptron) | 09 |
| 14 | `skill_14_yield_rate_anomaly_detection` | 分析 | US-09 | 隨機森林 | 10 |
| 15 | `skill_15_feature_importance_ranking` | 分析 | US-09 | 吉尼不純度下降量 (MDI) | 10 |
| 16 | `skill_16_root_cause_attribution_report` | 分析 | US-09 | 結果整合報告（無新演算法） | 10 |
| 17 | `skill_17_steel_surface_defect_classify` | 分析 | US-10 | CART 決策樹 | 11 |
| 18 | `skill_18_defect_geometric_feature_eval` | 分析 | US-10 | 決策樹吉尼重要度 | 11 |
| 19 | `skill_19_decision_tree_rule_extraction` | 分析 | US-11 | 代價複雜度剪枝 + IF-THEN 規則 | 11 |
| 20 | `skill_20_process_parameter_kmeans` | 分析 | US-12 | K 平均分群 | 12 |
| 21 | `skill_21_elbow_method_optimal_k` | 分析 | US-12 | 手肘法 (SSE) | 12 |
| 22 | `skill_22_spc_control_limit_monitoring` | 分析 | US-13 | SPC (Mean ± 3σ) | 12 |
| 23 | `skill_23_ipi_mlp_forecast` | 分析 | US-14 | 多層類神經網路 (MLP，真實訓練) | 13 |
| 24 | `skill_24_preventive_maintenance_hierarchy` | 分析 | US-15 | 凝聚階層式分群 | 13 |
| 25 | `skill_25_factory_risk_dendrogram_eval` | 分析 | US-15 | Dendrogram 切割與評估報告 | 13 |
| 26 | `skill_26_document_catalog_query` | 檢索 | US-17 | SQLite 元資料過濾 | 02 |
| 27 | `skill_27_kb_import_pipeline` | 匯入 | US-18 | 正則清洗 + SHA-256 去重 + 滑動視窗切片 | 03 |
| 28 | `skill_28_data_freshness_check` | 維運與評估 | US-19 | 落後月數 + 時間指數衰減 | 04 |
| 29 | `skill_29_retrieval_quality_eval` | 維運與評估 | US-19 | Hit@3、MRR | 04 |

**頁面 → Skill 鏈（呼叫順序）**

| 頁面 | Skill 鏈 |
| :--- | :--- |
| 01 | skill_01 → AnythingLLM 產生回答 |
| 02 | skill_26 |
| 03 | skill_27 → skill_03 → 重跑模型類 Skill |
| 04 | skill_28、skill_29 |
| 05 | skill_01（關鍵字）／skill_02（機械資格） |
| 06 | skill_03 → skill_04 → skill_05 |
| 07 | skill_06 → skill_07 → skill_08 |
| 08 | skill_10 → skill_09 → skill_11 |
| 09 | skill_12 → skill_13 |
| 10 | skill_14 → skill_15 → skill_16 |
| 11 | skill_17 → skill_18 → skill_19 |
| 12 | skill_21 → skill_20 → skill_22 |
| 13 | skill_23；skill_24 → skill_25 |

---

## 二、 各 Skill 詳細規格與輸入輸出 JSON 範例

### Skill 01: `skill_01_tool_regulation_search`
* **功能**：查詢字串轉 TF-IDF 向量，與法規、CNS 標準、SOP 切片算餘弦相似度，KNN 取 Top-K；最高分低於門檻（預設 0.10）回查無資料。
* **輸入**：`{"query_text": "電動工具安全規範", "top_k": 3, "threshold": 0.10}`
* **輸出**：
  ```json
  {"top_k_regulations": [{"regulation_id": "CNS-1234", "title": "電動工具安全規範", "similarity_score": 0.89}], "found": true, "status": "success", "steps": []}
  ```

### Skill 02: `skill_02_machine_qualification_match`
* **功能**：以 Jaccard 集合相似度比對使用者具備的資格與法規要求的資格集合，列出缺少項目；門檻預設 0.20。
* **輸入**：`{"equipment_type": "衝壓剪切機械", "user_credentials": ["教育訓練結業證書"], "threshold": 0.20}`
* **輸出**：
  ```json
  {"matched_qualification": "衝壓剪切機械操作人員資格條文", "jaccard_score": 0.85, "missing_items": [], "status": "success", "steps": []}
  ```

### Skill 03: `skill_03_sensor_data_preprocessing`
* **功能**：以訓練集平均與母體標準差對感測器數據做 Z-Score；標準差為 0 時回錯誤。
* **輸入**：`{"raw_values": [1500, 2.8, 75.0, 85.0]}`
* **輸出**：
  ```json
  {"standardized_values": [0.12, -0.45, 1.1, 0.88], "status": "success", "steps": []}
  ```

### Skill 04: `skill_04_equipment_rul_prediction`
* **功能**：多元線性迴歸 (OLS) 預測 RUL，訓練與測試誤差分開列；輸出標「僅供參考」。
* **輸入**：`{"operating_hours": 1500, "vibration": 2.8, "temperature": 75, "load_rate": 85}`
* **輸出**：
  ```json
  {"predicted_rul_hours": 320.5, "eval_metrics": {"train": {"mae": 7.9, "rmse": 10.4}, "test": {"mae": 8.3, "rmse": 11.2}}, "status": "success", "steps": []}
  ```

### Skill 05: `skill_05_degradation_feature_attribution`
* **功能**：拆解 OLS 係數（標準化後）評估各感測器對衰退的影響。
* **輸入**：`{"model_id": "OLS_RUL_V1"}`
* **輸出**：
  ```json
  {"regression_coefficients": {"vibration": -12.4, "temperature": -5.2, "load_rate": -2.1}, "status": "success", "steps": []}
  ```

### Skill 06: `skill_06_failure_probability_calc`
* **功能**：邏輯迴歸 Sigmoid 計算突發故障機率。
* **輸入**：`{"recency_days": 45, "alarms_90d": 12, "pressure": 1.8}`
* **輸出**：
  ```json
  {"failure_probability": 0.84, "status": "success", "steps": []}
  ```

### Skill 07: `skill_07_risk_level_classification`
* **功能**：計算勝算比並劃分紅黃綠燈號（燈號門檻來自 skill_08 或設定檔）。
* **輸入**：`{"failure_probability": 0.84}`
* **輸出**：
  ```json
  {"odds_ratio": 5.25, "risk_level": "RED", "status": "success", "steps": []}
  ```

### Skill 08: `skill_08_cost_sensitive_threshold_tuning`
* **功能**：掃描門檻 0.00–1.00，依停機損失與誤報成本算總成本，輸出最低者。
* **輸入**：`{"cost_downtime": 50000, "cost_inspection": 2000}`
* **輸出**：
  ```json
  {"optimal_threshold": 0.65, "total_cost_min": 12000, "fp": 4, "fn": 0, "status": "success", "steps": []}
  ```

### Skill 09: `skill_09_similar_repair_case_search`
* **功能**：以 skill_10 產生的特徵向量，用歐氏距離 KNN 取 Top 3 工單，距離換算相似度 $1/(1+d)$。
* **輸入**：`{"feature_vector": [2.8, 75.0, 1.8], "top_k": 3}`
* **輸出**：
  ```json
  {"top3_similar_cases": [{"case_id": "MA-2024-089", "similarity": 0.94}], "status": "success", "steps": []}
  ```

### Skill 10: `skill_10_error_code_feature_matching`
* **功能**：故障碼對照故障模式，並把輸入特徵標準化、套用權重，輸出給 skill_09。
* **輸入**：`{"error_code": "E-8021", "raw_features": [2.8, 75.0, 1.8]}`
* **輸出**：
  ```json
  {"matched_pattern": "MOTOR_OVERHEAT", "feature_vector": [0.31, 1.12, -0.05], "status": "success", "steps": []}
  ```

### Skill 11: `skill_11_spare_parts_recommendation`
* **功能**：物品協同過濾，以工單 × 備品領用矩陣算備品間餘弦相似度，加權推薦。
* **輸入**：`{"case_ids": ["MA-2024-089"]}`
* **輸出**：
  ```json
  {"recommended_parts": [{"part_id": "SP-8821", "score": 0.88, "stock_status": "NORMAL"}], "status": "success", "steps": []}
  ```

### Skill 12: `skill_12_repair_log_entry_validation`
* **功能**：正則檢查欄位格式（設備 ID、故障碼、日期）與數值臨界範圍；不通過即停止，不送 skill_13。
* **輸入**：`{"equipment_id": "EQ-PRESS-01", "error_code": "E-8021", "current_a": 45.2, "pressure_mpa": 2.1}`
* **輸出**：
  ```json
  {"is_valid": true, "invalid_fields": [], "message": "FIELD_VALIDATION_PASSED", "status": "success", "steps": []}
  ```

### Skill 13: `skill_13_error_code_perceptron_check`
* **功能**：單層感知器二元劃分；有標籤時判錯即更新權重。
* **輸入**：`{"features": [45.2, 2.1]}`
* **輸出**：
  ```json
  {"validation_result": 0, "status": "COMPLIANT", "updated_weights": {"w1": 0.45, "w2": -0.12, "bias": 0.05}, "steps": []}
  ```

### Skill 14: `skill_14_yield_rate_anomaly_detection`
* **功能**：隨機森林多樹投票判斷批次品質是否異常。
* **輸入**：`{"batch_params": [180.5, 42.0, 15.2], "n_trees": 100}`
* **輸出**：
  ```json
  {"yield_rate_prediction": 0.942, "ensemble_prediction": 0, "status": "success", "steps": []}
  ```

### Skill 15: `skill_15_feature_importance_ranking`
* **功能**：彙總各樹吉尼不純度下降量 (MDI) 並排序。
* **輸入**：`{"batch_id": "B-2026-10"}`
* **輸出**：
  ```json
  {"feature_importance": [{"feature": "temp", "importance": 0.42}, {"feature": "cooling", "importance": 0.31}], "status": "success", "steps": []}
  ```

### Skill 16: `skill_16_root_cause_attribution_report`
* **功能**：整合 skill_14、15 結果產生根因報告（只代表相關）。
* **輸入**：`{"batch_id": "B-2026-10"}`
* **輸出**：
  ```json
  {"root_cause_feature": "temp", "risk_score": 0.82, "action_recommendation": "檢查加熱段溫控", "status": "success", "steps": []}
  ```

### Skill 17: `skill_17_steel_surface_defect_classify`
* **功能**：CART 決策樹（吉尼）多類別分類鋼板缺陷。
* **輸入**：`{"area": 150, "aspect_ratio": 4.2, "contrast": 85}`
* **輸出**：
  ```json
  {"defect_class": "Scratch", "confusion_matrix": [[45, 2], [1, 48]], "status": "success", "steps": []}
  ```

### Skill 18: `skill_18_defect_geometric_feature_eval`
* **功能**：由決策樹各節點吉尼下降量計算面積、長寬比、對比度的影響力。
* **輸入**：`{"model_id": "CART_DEFECT_V1"}`
* **輸出**：
  ```json
  {"feature_importance": {"area": 0.51, "aspect_ratio": 0.37, "contrast": 0.12}, "status": "success", "steps": []}
  ```

### Skill 19: `skill_19_decision_tree_rule_extraction`
* **功能**：代價複雜度剪枝，以測試集選 α，並導出白盒 IF-THEN 規則。
* **輸入**：`{"alpha_threshold": 0.01}`
* **輸出**：
  ```json
  {"rule_path": "IF area > 120 AND aspect_ratio > 3.5 THEN Scratch", "accuracy_before": 0.95, "accuracy_after": 0.93, "status": "success", "steps": []}
  ```

### Skill 20: `skill_20_process_parameter_kmeans`
* **功能**：以 skill_21 選出的 K 對製程參數 z 分數做 K-Means。
* **輸入**：`{"z_scores": [[0.12, -0.45], [1.2, 0.88]], "k": 3}`
* **輸出**：
  ```json
  {"cluster_centers": [[0.12, -0.45], [1.2, 0.88]], "labels": [0, 1], "sse": 42.5, "status": "success", "steps": []}
  ```

### Skill 21: `skill_21_elbow_method_optimal_k`
* **功能**：算 k=1 到 max_k 的最小 SSE（多組起始中心取最好），找轉折點。
* **輸入**：`{"max_k": 8, "data": [[0.12, -0.45], [1.2, 0.88]]}`
* **輸出**：
  ```json
  {"optimal_k": 3, "sse_by_k": [110.0, 75.3, 42.5], "status": "success", "steps": []}
  ```

### Skill 22: `skill_22_spc_control_limit_monitoring`
* **功能**：計算 Mean ± 3σ 管制界限並標出超界點。
* **輸入**：`{"data_series": [0.12, -0.45, 1.2, 3.5, -3.2]}`
* **輸出**：
  ```json
  {"spc_limits": {"ucl": 3.0, "lcl": -3.0}, "outliers_count": 2, "status": "success", "steps": []}
  ```

### Skill 23: `skill_23_ipi_mlp_forecast`（原 `skill_23_production_index_hierarchical`）
* **功能**：以歷史月度 IPI 等變數**真實訓練**一個單隱藏層 MLP（反向傳播），依時間切分訓練／測試，並與「延續上月」基準比較；輸出標「僅供參考」。
* **輸入**：`{"historical_ipi": [105.2, 106.1, 107.0], "epochs": 500, "learning_rate": 0.01}`
* **輸出**：
  ```json
  {"ipi_forecast_next_quarter": [108.5, 109.2, 110.1], "training_loss_final": 0.012, "loss_history": [0.9, 0.3, 0.012], "test_rmse": 1.8, "baseline_rmse": 2.1, "status": "success", "steps": []}
  ```

### Skill 24: `skill_24_preventive_maintenance_hierarchy`
* **功能**：依設備風險指標建距離矩陣，凝聚法建立階層樹。
* **輸入**：`{"equipment_risk_matrix": [[0.8, 0.2], [0.1, 0.9]], "linkage": "average"}`
* **輸出**：
  ```json
  {"merge_history": [[0, 1, 0.42]], "status": "success", "steps": []}
  ```

### Skill 25: `skill_25_factory_risk_dendrogram_eval`
* **功能**：依距離門檻切割 skill_24 的樹，輸出風險階層、各群設備與預防維護排程。
* **輸入**：`{"distance_threshold": 0.5}`
* **輸出**：
  ```json
  {"clusters_count": 3, "dendrogram_tree": {"node_id": 0, "children": [1, 2]}, "preventive_schedule": [{"group": 1, "action_week": 2}], "risk_summary": "高風險集中在衝壓區", "status": "success", "steps": []}
  ```

### Skill 26: `skill_26_document_catalog_query`（新增）
* **功能**：以 `sqlite3` 依角色（民眾只看公開）、類別、日期、關鍵字查詢文件元資料。
* **輸入**：`{"role": "public", "categories": ["CNS"], "start_date": "2026-01-01", "end_date": "2026-10-31", "keyword": "電動工具"}`
* **輸出**：
  ```json
  {"documents": [{"doc_id": "DOC-CNS-1234", "source_name": "CNS 手持式電動工具安全規範", "updated_at": "2026-10-15", "license_type": "政府資料開放授權 (OGDL v1.0)", "content_preview": "…", "source_url": "…"}], "total": 1, "status": "success", "steps": []}
  ```

### Skill 27: `skill_27_kb_import_pipeline`（新增）
* **功能**：讀取上傳檔 → 正則清洗 → SHA-256 去重 → 筆數核對 → 滑動視窗切片並寫入索引；每步狀態與失敗原因寫入匯入紀錄。
* **輸入**：`{"files": ["repair_log_2026Q3.csv"], "rules": {"strip_noise": true, "normalize_datetime": true, "dedupe": true, "chunk_size": 500, "overlap": 50}}`
* **輸出**：
  ```json
  {"import_progress_pct": 100, "rows_read": 1463, "rows_cleaned_count": 1280, "duplicate_rate_pct": 12.5, "chunks_created_count": 342, "failures": [], "status": "success", "steps": []}
  ```

### Skill 28: `skill_28_data_freshness_check`（新增）
* **功能**：讀各資料集最新日期，依基準日算落後月數與時間衰減權重 $e^{-\lambda\Delta t}$，超過門檻（預設 3 個月）提醒。
* **輸入**：`{"today": "2026-11-11", "max_lag_months": 3, "decay_lambda": 0.1}`
* **輸出**：
  ```json
  {"datasets": [{"name": "職安法規", "latest": "2026-06", "lag_months": 5, "weight": 0.61, "warning": true}], "data_freshness_status": "需更新", "status": "success", "steps": []}
  ```

### Skill 29: `skill_29_retrieval_quality_eval`（新增）
* **功能**：以 20 題標準問答呼叫 skill_01，計算 Top-3 命中率、MRR，列出錯誤案例。
* **輸入**：`{"gold_set": "data/eval/gold_20.json", "top_k": 3}`
* **輸出**：
  ```json
  {"hit_rate_top3_pct": 90.0, "mrr": 0.81, "error_cases_list": [{"qid": "Q07", "query": "…", "expected": "…", "actual": "…", "error_type": "偏離"}], "status": "success", "steps": []}
  ```
