# 製造業知識庫網站 - 角色與演算法選擇規格書 (Step 01 完整版・v2 統一版)

> **v2 修訂重點**：統一為 **13 頁**選單（01–04 共同網頁、05–13 主題網頁）；新增 **管理者** 角色；Skill 由 25 個擴充為 **29 個**（新增共同網頁用的 Skill 26–29）；`skill_23` 更名為 `skill_23_ipi_mlp_forecast`。完整修訂對照見 `CHANGELOG_v2.md`。

---

## 零、 13 頁選單總表（全專案唯一標準，其他文件一律以此為準）

| 頁碼 | 頁面名稱 | 類型 | 網址 (URL) | 檔名 | 主要角色 |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 01 | 製造知識庫檢索與智慧問答頁 | 共同網頁 1 | `/knowledge/chat` | `page01_knowledge_chat.html` | 一般民眾、設備維修工程師、品質與製程工程師 |
| 02 | 製造規範與技術文件收錄頁 | 共同網頁 2 | `/knowledge/documents` | `page02_doc_collection.html` | 一般民眾、各工程師 |
| 03 | 工廠圖資與維修履歷匯入整理頁 | 共同網頁 3 | `/knowledge/import` | `page03_import_cleaning.html` | **管理者**（工程師可上傳檔案） |
| 04 | 製造知識庫維運與回答品質評估頁 | 共同網頁 4 | `/knowledge/ops-eval` | `page04_ops_eval.html` | **管理者**（廠長唯讀） |
| 05 | 公開法規與商品檢驗查詢頁 | 主題網頁 1 | `/regulations/search` | `page05_regulations_search.html` | 一般民眾 |
| 06 | 設備壽命預測頁 | 主題網頁 2 | `/equipment/rul-prediction` | `page06_rul_prediction.html` | 設備維修工程師 |
| 07 | 設備突發故障風險評估頁 | 主題網頁 3 | `/equipment/failure-risk` | `page07_failure_risk.html` | 設備維修工程師 |
| 08 | 歷史維修案例檢索與備品推薦頁 | 主題網頁 4 | `/equipment/case-retrieval` | `page08_case_retrieval.html` | 設備維修工程師 |
| 09 | 維修案例登錄與故障碼驗證頁 | 主題網頁 5 | `/equipment/repair-log` | `page09_repair_log.html` | 設備維修工程師 |
| 10 | 品質異常根本原因分析頁 | 主題網頁 6 | `/quality/root-cause` | `page10_root_cause.html` | 品質與製程工程師 |
| 11 | 鋼板表面缺陷分類與特徵評估頁 | 主題網頁 7 | `/quality/steel-defects` | `page11_steel_defects.html` | 品質與製程工程師 |
| 12 | 製程參數分群與 SPC 管制監控頁 | 主題網頁 8 | `/quality/spc-clustering` | `page12_spc_clustering.html` | 品質與製程工程師 |
| 13 | 智慧生產指數預測與管理頁 | 主題網頁 9 | `/production/index-forecast` | `page13_index_forecast.html` | 生產排程主管 / 廠長 |

---

## 一、 平台角色、日常業務與選單頁面直接對應表

| 角色類別 | 日常業務 | 在知識庫裡能做什麼 | 對應的選單頁面 |
| :---- | :---- | :---- | :---- |
| **一般民眾** | 查詢市售電動工具檢驗規定、操作危險性機械之法規資格 | 智慧問答（公開範圍）、瀏覽公開文件、查詢商品檢驗與 CNS 標準、職安法規與操作人員資格摘要 | 01、02（公開文件）、05 |
| **設備維修工程師** | 診斷產線設備故障碼、尋找過往維修經驗、記錄維修時間軸 | 預測設備剩餘壽命、評估故障風險與預警門檻、檢索 Top 3 相似案例與推薦備品、登錄維修紀錄並即時驗證；可上傳維修履歷檔案 | 01、02、03（上傳）、05、06、07、08、09 |
| **品質與製程工程師** | 監控生產良率與缺陷率、分析 SPC 管制圖異常、追查鋼板表面缺陷成因 | 根本原因分析、鋼板缺陷分類與白盒規則、製程參數分群與 SPC 管制圖；可上傳製程數據檔案 | 01、02、03（上傳）、05、10、11、12 |
| **生產排程主管 / 廠長** | 評估未來工業生產指數走勢、規劃設備預防性維護時程 | 生產指數預測、預防維護排程；跨頁唯讀調閱設備與品質頁、唯讀查看維運狀態 | 01、02、04（唯讀）、05–13（06–12 唯讀） |
| **管理者**（知識庫管理者 / 系統維運人員） | 維護知識庫資料、執行匯入與清理、監控資料新鮮度與回答品質 | 執行資料匯入整理（含重算模型結果檔）、檢查資料新鮮度、重跑檢索命中率評估；可使用其他角色的所有功能 | 01–13（全部），其中 03、04 為主要負責頁 |

---

## 二、 演算法取捨與業務情境對應總表

| 平台角色 | 業務情境 | 用在哪個步驟 | 選用演算法 | 輸入資料 | 輸出 (標準 JSON 格式) | 選擇的原因 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **一般民眾** | 查詢市售電動工具檢驗規定與操作危險性機械之法規資格 | **第二步**：法規條文與檢驗資格之文字特徵距離比對 | **K 近鄰演算法 (KNN)** 與 **餘弦相似度 / Jaccard 相似度** | 使用者查詢字串、公開法規與 CNS 標準 TF-IDF 特徵矩陣、操作資格集合 | `{"top_k_regulations": [{"regulation_id": "CNS-1234", "title": "電動工具安全規範", "similarity_score": 0.89}], "status": "success"}` | 計算直觀且不需預訓練模型，適合中小型公開法規文本；分數可解釋，並可用門檻做「查無資料」防呆。 |
| **設備維修工程師** | 預測設備剩餘使用壽命 (RUL) | **第三步**：根據累積運轉時數與感測器數據進行剩餘壽命數值迴歸預測 | **多元線性迴歸 (Multiple Linear Regression)** / **最小平方法 (OLS)** | 運轉時數 (`operating_hours`)、振動值 (`vibration`)、溫度 (`temperature`)、負載率 (`load_rate`) | `{"predicted_rul_hours": 320.5, "regression_coefficients": {"vibration": -12.4, "temperature": -5.2}, "eval_metrics": {"mae": 8.3, "rmse": 11.2}}` | 一次算出閉式解，迴歸係數可直接說明各感測器對衰退的線性影響。 |
| **設備維修工程師** | 評估設備突發故障風險機率與預警燈號 | **第四步**：將特徵壓為故障機率，並結合維修與停機成本決定最佳預警門檻 | **邏輯迴歸 (Logistic Regression)** 與 **門檻成本取捨 (Cost-sensitive Tuning)** | 距上次維修天數 (`recency_days`)、近 90 天警報次數 (`alarms_90d`)、運轉壓力 (`pressure`) | `{"failure_probability": 0.84, "odds_ratio": 5.25, "risk_level": "RED", "optimal_threshold": 0.65, "total_cost_min": 12000}` | Sigmoid 把分數轉成 0–1 機率；漏報（突發停機）代價遠高於誤報（派員檢修），以成本掃描找出最省錢的門檻。 |
| **設備維修工程師** | 尋找過往維修經驗與推薦故障處理備品 | **第二步**：依故障特徵距離搜尋近鄰案例，再以備品共現矩陣計算物品相似度 | **K 近鄰 (KNN - 歐氏距離)** 與 **物品協同過濾 (Item-based CF)** | 故障碼 (`error_code`)、故障物理特徵向量、歷史工單備品領用矩陣 | `{"top3_similar_cases": [{"case_id": "MA-2024-089", "similarity": 0.94}], "recommended_parts": [{"part_id": "SP-8821", "score": 0.88}]}` | KNN 依物理特徵距離找最相似案例；物品協同過濾依歷史領用推薦常一起更換的備品。 |
| **設備維修工程師** | 記錄維修時間軸與即時故障碼邏輯驗證 | **第一步**：案例登錄時，對故障碼與工單數值特徵執行二元劃分驗證 | **單層感知器 (Perceptron)** | 即時電流 (`current`)、壓力 (`pressure`)、歷史合規標籤 | `{"validation_result": 0, "status": "COMPLIANT", "updated_weights": {"w1": 0.45, "w2": -0.12, "bias": 0.05}}` | 結構極簡，專門處理線性可分的快速二元驗證，只在判錯時修正權重，適合即時防呆。 |
| **品質與製程工程師** | 監控生產良率並追查品質異常根本原因 | **第三步**：建立多棵決策樹並計算各製程特徵之吉尼不純度下降量排序 | **隨機森林 (Random Forest)** 與 **特徵重要度 (MDI)** | 加熱溫度 `temp`、軋延速度 `speed`、冷卻水流量 `cooling`、品質標籤 (`0:良品 / 1:不良品`) | `{"feature_importance": [{"feature": "temp", "importance": 0.42}, {"feature": "cooling", "importance": 0.31}], "ensemble_prediction": 1}` | 自助抽樣加多樹投票降低單棵樹過擬合，並輸出特徵重要度鎖定根因（只代表相關，不代表因果）。 |
| **品質與製程工程師** | 分析鋼板表面缺陷成因與評估幾何/光學特徵 | **第二步**：依幾何與光學特徵，以吉尼係數逐層劃分缺陷類別 | **決策樹 (CART)** 與 **代價複雜度剪枝 (Pruning)** | 缺陷面積 `area`、長寬比 `aspect_ratio`、灰階對比度 `contrast` | `{"defect_class": "Scratch", "rule_path": "IF area > 120 AND aspect_ratio > 3.5 THEN Scratch", "confusion_matrix": [[45, 2], [1, 48]]}` | 白盒特性，推理路徑可直接轉成規則；剪枝防止死背訓練資料。 |
| **品質與製程工程師** | 分析 SPC 管制圖異常與製程參數分群 | **第二步**：參數 z 分數無監督聚類；**第三步**：計算管制界限 | **K 平均分群 (K-Means)** + **手肘法** + **SPC 管制圖 (Mean ± 3σ)** | 標準化製程參數 z 分數（`temp_z`、`press_z`） | `{"optimal_k": 3, "cluster_centers": [[0.12, -0.45], [1.2, 0.88]], "sse": 42.5, "spc_limits": {"ucl": 3.0, "lcl": -3.0}, "outliers_count": 2}` | 手肘法客觀決定群數；±3σ 管制圖區分正常波動與製程異常。 |
| **生產排程主管 / 廠長** | 評估未來工業生產指數走勢 | **第二步**：以歷史月度數據訓練多層網路，反向傳播更新權重 | **多層類神經網路 (MLP)** / **前向與反向傳播** | 歷史工業生產指數 (`IPI`)、出口訂單額、設備稼動率、季節 dummy | `{"ipi_forecast_next_quarter": [108.5, 109.2, 110.1], "training_loss_final": 0.012, "convergence_epoch": 350}` | 隱藏層與非線性激活可捕捉非線性關係。**實作要求：真實訓練**（以時間切分訓練/測試，並與「延續上月」基準比較）。 |
| **生產排程主管 / 廠長** | 規劃設備預防性維護時程 | **第二步**：依設備故障率與運轉指標建立風險距離矩陣並凝聚分群 | **凝聚階層式分群 (Hierarchical Clustering)** | 各設備故障率、MTBF、運轉負載等指標 | `{"clusters_count": 3, "preventive_schedule": [{"group": 1, "action_week": 2}]}` | 不需事先指定群數，樹狀圖可直接看出設備風險階層，據以排定保養視窗。 |
| **管理者** | 匯入資料、監控資料新鮮度與回答品質 | 匯入時清理、去重、切片；維運時算落後月數與檢索命中率 | **非課堂演算法**（正則清洗、SHA-256 雜湊去重、滑動視窗切片、Hit@3 / MRR） | 上傳檔案（PDF/CSV/MD）、各資料集最新日期、20 題標準問答 | `{"rows_cleaned_count": 1280, "duplicate_rate_pct": 12.5, "hit_rate_top3_pct": 90.0, "mrr": 0.81}` | 用標準函式庫即可完成，結果可重現；屬平台維運機制，不假裝成課堂演算法。 |

> 表中 JSON 數字皆為**設計示意值**，Skill 以真實資料執行後須更新。

---

## 三、 業務地圖（29 個 Skill）

| 角色 | 日常業務 | 演算法 / 機制 | Skill | 對應的頁面 |
| :--- | :--- | :--- | :--- | :--- |
| 一般民眾 / 工程師 | 用自然語言問製造知識 | KNN + 餘弦相似度（＋AnythingLLM 產生回答） | `skill_01_tool_regulation_search` | 01、05 |
| 一般民眾 | 查詢危險性機械操作資格 | KNN + Jaccard 相似度 | `skill_02_machine_qualification_match` | 05 |
| 設備維修工程師 | 感測器數據前處理 | Z-Score 標準化 | `skill_03_sensor_data_preprocessing` | 06（03 匯入時亦呼叫） |
| 設備維修工程師 | 預測剩餘壽命 (RUL) | 多元線性迴歸 (OLS) | `skill_04_equipment_rul_prediction` | 06 |
| 設備維修工程師 | 找出影響衰退的感測器 | OLS 係數貢獻度拆解 | `skill_05_degradation_feature_attribution` | 06 |
| 設備維修工程師 | 評估突發故障機率 | 邏輯迴歸 (Sigmoid) | `skill_06_failure_probability_calc` | 07 |
| 設備維修工程師 | 換算風險燈號 | 勝算比 + 燈號劃分 | `skill_07_risk_level_classification` | 07 |
| 設備維修工程師 | 決定最佳預警門檻 | 門檻成本取捨 | `skill_08_cost_sensitive_threshold_tuning` | 07 |
| 設備維修工程師 | 找 Top 3 相似維修案例 | KNN（歐氏距離） | `skill_09_similar_repair_case_search` | 08 |
| 設備維修工程師 | 故障碼轉成特徵向量 | 故障碼對照 + 特徵標準化加權 | `skill_10_error_code_feature_matching` | 08 |
| 設備維修工程師 | 推薦故障處理備品 | 物品協同過濾 (Item-based CF) | `skill_11_spare_parts_recommendation` | 08 |
| 設備維修工程師 | 維修紀錄欄位防呆 | 正則表達式 + 臨界值檢查 | `skill_12_repair_log_entry_validation` | 09 |
| 設備維修工程師 | 即時合規判斷 | 單層感知器 (Perceptron) | `skill_13_error_code_perceptron_check` | 09 |
| 品質與製程工程師 | 判斷批次品質是否異常 | 隨機森林 | `skill_14_yield_rate_anomaly_detection` | 10 |
| 品質與製程工程師 | 排出影響品質的製程參數 | 吉尼不純度下降量 (MDI) | `skill_15_feature_importance_ranking` | 10 |
| 品質與製程工程師 | 產生根因報告 | 結果整合（無新演算法） | `skill_16_root_cause_attribution_report` | 10 |
| 品質與製程工程師 | 鋼板缺陷分類 | CART 決策樹 | `skill_17_steel_surface_defect_classify` | 11 |
| 品質與製程工程師 | 評估幾何/光學特徵影響力 | 決策樹吉尼重要度 | `skill_18_defect_geometric_feature_eval` | 11 |
| 品質與製程工程師 | 剪枝並導出白盒規則 | 代價複雜度剪枝 + IF-THEN 規則 | `skill_19_decision_tree_rule_extraction` | 11 |
| 品質與製程工程師 | 製程參數分群 | K 平均分群 | `skill_20_process_parameter_kmeans` | 12 |
| 品質與製程工程師 | 決定分幾群 | 手肘法 (SSE) | `skill_21_elbow_method_optimal_k` | 12 |
| 品質與製程工程師 | 管制圖異常監控 | SPC (Mean ± 3σ) | `skill_22_spc_control_limit_monitoring` | 12 |
| 生產排程主管 / 廠長 | 預測工業生產指數 | 多層類神經網路 (MLP) | `skill_23_ipi_mlp_forecast` | 13 |
| 生產排程主管 / 廠長 | 規劃預防維護 | 凝聚階層式分群 | `skill_24_preventive_maintenance_hierarchy` | 13 |
| 生產排程主管 / 廠長 | 風險樹狀圖與報告 | Dendrogram 切割與評估 | `skill_25_factory_risk_dendrogram_eval` | 13 |
| 一般民眾 / 工程師 | 瀏覽收錄文件與出處 | SQLite 元資料過濾（標準函式庫） | `skill_26_document_catalog_query` | 02 |
| 管理者 | 匯入並整理新資料 | 正則清洗 + SHA-256 去重 + 滑動視窗切片 | `skill_27_kb_import_pipeline` | 03 |
| 管理者 | 檢查資料新不新 | 落後月數 + 時間指數衰減 | `skill_28_data_freshness_check` | 04 |
| 管理者 | 評估檢索與回答品質 | Hit@3、MRR（20 題標準問答） | `skill_29_retrieval_quality_eval` | 04 |
