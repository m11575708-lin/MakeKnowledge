try:
    from mcp.server.fastmcp import FastMCP            # mcp 1.x
except ImportError:                                    # mcp 2.x 將 FastMCP 改名為 MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
from typing import List, Optional
import importlib
import json
import os
import sys
import traceback

# 將專案根目錄加入系統路徑，確保能順利匯入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# 注意：MCP 以 STDIO 通訊，stdout 專供協定使用。
# 所有除錯訊息一律輸出到 stderr，絕對不要在這支程式或 Skill 中 print 到 stdout。
def _safe_skill(module_name: str, func_name: str):
    """優先從 skills/ 匯入，其次專案根目錄；失敗時回傳會輸出錯誤 JSON 的備用函數。"""
    for dotted in (f"skills.{module_name}", module_name):
        try:
            return getattr(importlib.import_module(dotted), func_name)
        except ImportError:
            continue
        except Exception:
            print(f"[匯入失敗] {dotted}:\n{traceback.format_exc()}", file=sys.stderr)
            break

    def _fallback(*_args, **_kwargs):
        return {
            "status": "error",
            "found": False,
            "answer_text": f"系統找不到或無法載入模組 {module_name}，請確認檔案已放入 skills/ 資料夾。",
            "steps": [],
        }

    return _fallback


search_tool_regulations = _safe_skill("skill_01_tool_regulation_search", "search_tool_regulations")
match_machine_qualification = _safe_skill("skill_02_machine_qualification_match", "match_machine_qualification")
preprocess_sensor_data = _safe_skill("skill_03_sensor_data_preprocessing", "preprocess_sensor_data")
predict_equipment_rul = _safe_skill("skill_04_equipment_rul_prediction", "predict_equipment_rul")
attribute_degradation_features = _safe_skill("skill_05_degradation_feature_attribution", "attribute_degradation_features")
calculate_failure_probability = _safe_skill("skill_06_failure_probability_calc", "calculate_failure_probability")
classify_risk_level = _safe_skill("skill_07_risk_level_classification", "classify_risk_level")
tune_cost_threshold = _safe_skill("skill_08_cost_sensitive_threshold_tuning", "tune_cost_threshold")
search_similar_repair_cases = _safe_skill("skill_09_similar_repair_case_search", "search_similar_repair_cases")
match_error_code_pattern = _safe_skill("skill_10_error_code_feature_matching", "match_error_code_pattern")
recommend_spare_parts = _safe_skill("skill_11_spare_parts_recommendation", "recommend_spare_parts")
validate_repair_log_entry = _safe_skill("skill_12_repair_log_entry_validation", "validate_repair_log_entry")
check_error_code_perceptron = _safe_skill("skill_13_error_code_perceptron_check", "check_error_code_perceptron")
detect_yield_anomaly = _safe_skill("skill_14_yield_rate_anomaly_detection", "detect_yield_anomaly")
rank_feature_importance = _safe_skill("skill_15_feature_importance_ranking", "rank_feature_importance")
build_root_cause_report = _safe_skill("skill_16_root_cause_attribution_report", "build_root_cause_report")
classify_steel_defect = _safe_skill("skill_17_steel_surface_defect_classify", "classify_steel_defect")
evaluate_defect_features = _safe_skill("skill_18_defect_geometric_feature_eval", "evaluate_defect_features")
extract_decision_tree_rules = _safe_skill("skill_19_decision_tree_rule_extraction", "extract_decision_tree_rules")
find_optimal_k = _safe_skill("skill_21_elbow_method_optimal_k", "find_optimal_k")
run_kmeans = _safe_skill("skill_20_process_parameter_kmeans", "run_kmeans")
monitor_spc = _safe_skill("skill_22_spc_control_limit_monitoring", "monitor_spc")
spc_load_data = _safe_skill("_spc_data", "load_data")
spc_standardize = _safe_skill("_spc_data", "standardize")
forecast_ipi_mlp = _safe_skill("skill_23_ipi_mlp_forecast", "forecast_ipi_mlp")
build_hierarchy = _safe_skill("skill_24_preventive_maintenance_hierarchy", "build_hierarchy")
evaluate_dendrogram = _safe_skill("skill_25_factory_risk_dendrogram_eval", "evaluate_dendrogram")
equipment_load_data = _safe_skill("_equipment_data", "load_data")
equipment_risk_matrix = _safe_skill("_equipment_data", "risk_matrix")
import_kb_files = _safe_skill("skill_27_kb_import_pipeline", "import_kb_files")
query_document_catalog = _safe_skill("skill_26_document_catalog_query", "query_document_catalog")
check_data_freshness = _safe_skill("skill_28_data_freshness_check", "check_data_freshness")
evaluate_retrieval_quality = _safe_skill("skill_29_retrieval_quality_eval", "evaluate_retrieval_quality")

# 初始化 FastMCP 伺服器（命名為 manufacturing_kb）
mcp = FastMCP("manufacturing_kb")


def _dump(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def skill_01_tool_regulation_search(query_text: str, threshold: float = 0.10) -> str:
    """
    製造規範與法規智慧檢索工具 (Skill 01)：
    根據自然語言查詢，比對廠內 SOP、職業安全衛生法規與 CNS 標準，
    回傳條理化解答、匹配相似度得分、參考來源以及完整的演算法透明度推導步驟。
    """
    return _dump(search_tool_regulations(query_text=query_text, threshold=threshold))


@mcp.tool()
def skill_02_machine_qualification_match(
    equipment_type: str = "衝壓剪切機械",
    user_credentials: Optional[List[str]] = None,
    query_text: str = "衝壓機操作人員資格與每日作業前安全檢點規定",
    threshold: float = 0.20
) -> str:
    """
    機械設備與操作資格比對工具 (Skill 02)：
    比對危險性機械設備（如衝壓剪切機械、升降機具）之法定操作人員資格與安全檢驗規定，
    回傳 Jaccard 相似度匹配指數、合格條文與演算法推導步驟。
    """
    return _dump(match_machine_qualification(
        equipment_type=equipment_type,
        user_credentials=user_credentials,
        query_text=query_text,
        threshold=threshold
    ))


@mcp.tool()
def skill_03_sensor_data_preprocessing(
    operating_hours: float = 1500,
    vibration: float = 2.8,
    temperature: float = 75,
    load_rate: float = 85
) -> str:
    """
    感測器數據前處理工具 (Skill 03)：
    對設備運轉時數、振動、溫度、負載率執行 Z-Score 標準化，
    並檢查輸入是否超出物理合理範圍或嚴重偏離訓練資料（外插防呆）。
    """
    return _dump(preprocess_sensor_data(raw_values={
        "operating_hours": operating_hours, "vibration": vibration,
        "temperature": temperature, "load_rate": load_rate,
    }))


@mcp.tool()
def skill_04_equipment_rul_prediction(
    operating_hours: float = 1500,
    vibration: float = 2.8,
    temperature: float = 75,
    load_rate: float = 85
) -> str:
    """
    設備剩餘使用壽命預測工具 (Skill 04)：
    以多元線性迴歸 (OLS 最小平方法) 預測剩餘壽命小時數，
    回傳 95% 預測區間、健康度燈號、測試集 MAE / RMSE / R² 與 5 步推導日誌。
    """
    return _dump(predict_equipment_rul(
        operating_hours=operating_hours, vibration=vibration,
        temperature=temperature, load_rate=load_rate
    ))


@mcp.tool()
def skill_05_degradation_feature_attribution(
    operating_hours: float = 1500,
    vibration: float = 2.8,
    temperature: float = 75,
    load_rate: float = 85
) -> str:
    """
    設備衰退特徵貢獻度拆解工具 (Skill 05)：
    拆解 OLS 迴歸係數，並計算本次工況下各感測器參數對壽命縮短或延長的貢獻小時數與佔比，
    指出最主要的衰退驅動因子。
    """
    return _dump(attribute_degradation_features(
        operating_hours=operating_hours, vibration=vibration,
        temperature=temperature, load_rate=load_rate
    ))


@mcp.tool()
def skill_06_failure_probability_calc(
    recency_days: float = 45,
    alarms_90d: float = 12,
    pressure: float = 1.8
) -> str:
    """
    設備突發故障機率計算工具 (Skill 06)：
    以邏輯迴歸 (Sigmoid) 將距上次維修天數、近 90 天警報次數（整數）與運轉壓力轉為 0~1 的故障機率，
    回傳測試集 AUC / Accuracy / Log-loss、各參數勝算比與 5 步推導日誌。
    """
    return _dump(calculate_failure_probability(
        recency_days=recency_days, alarms_90d=alarms_90d, pressure=pressure
    ))


@mcp.tool()
def skill_07_risk_level_classification(
    failure_probability: float = 0.84,
    yellow_threshold: float = 0.40,
    red_threshold: float = 0.70
) -> str:
    """
    勝算比與風險燈號劃分工具 (Skill 07)：
    由故障機率計算勝算比 Odds = p/(1-p)，並依門檻劃分 GREEN / YELLOW / RED 預警燈號與處置建議。
    """
    return _dump(classify_risk_level(
        failure_probability=failure_probability,
        yellow_threshold=yellow_threshold, red_threshold=red_threshold
    ))


@mcp.tool()
def skill_08_cost_sensitive_threshold_tuning(
    cost_downtime: float = 50000,
    cost_inspection: float = 2000,
    failure_probability: Optional[float] = None
) -> str:
    """
    代價敏感預警門檻最佳化工具 (Skill 08)：
    依停機損失與誤報檢修成本矩陣，掃描門檻 θ 並極小化 Cost = C_down·FN + C_inspect·FP，
    回傳最佳預警門檻、最低總成本、與「全部檢修 / 完全不預警」等基準策略的比較。
    """
    return _dump(tune_cost_threshold(
        cost_downtime=cost_downtime, cost_inspection=cost_inspection,
        failure_probability=failure_probability
    ))


@mcp.tool()
def skill_09_similar_repair_case_search(
    vibration: float = 2.8,
    temperature: float = 75.0,
    pressure: float = 1.8,
    top_k: int = 3,
    error_code: Optional[str] = None,
    restrict_to_error_code: bool = False
) -> str:
    """
    相似維修案例檢索工具 (Skill 09)：
    以 KNN（Z-Score 標準化後的加權歐氏距離）自歷史維修工單檢索最相似的 Top-K 案例，
    回傳案例編號、相似度、故障描述、排除步驟、領用備品與逐特徵比較。
    """
    return _dump(search_similar_repair_cases(
        feature_vector=[vibration, temperature, pressure], top_k=top_k,
        error_code=error_code, restrict_to_error_code=restrict_to_error_code
    ))


@mcp.tool()
def skill_10_error_code_feature_matching(
    error_code: str = "E-8021",
    vibration: Optional[float] = None,
    temperature: Optional[float] = None,
    pressure: Optional[float] = None
) -> str:
    """
    故障碼特徵比對工具 (Skill 10)：
    依故障碼彙整歷史案例的典型特徵，以逆變異數校正特徵權重，並計算目前特徵與該故障模式的吻合度（高斯核信心度）。
    振動、溫度、壓力三者皆提供時才會計算吻合度。
    """
    vec = [vibration, temperature, pressure]
    return _dump(match_error_code_pattern(
        error_code=error_code,
        feature_vector=vec if all(v is not None for v in vec) else None
    ))


@mcp.tool()
def skill_11_spare_parts_recommendation(case_id: str = "MA-2024-089", top_n: int = 5) -> str:
    """
    維修備品推薦工具 (Skill 11)：
    以物品協同過濾 (Item-based CF) 分析歷史工單的備品共現關係，
    針對指定案例推薦備品、推薦分數與庫存標籤（NORMAL / LOW / OUT）。
    """
    return _dump(recommend_spare_parts(case_id=case_id, top_n=top_n))


@mcp.tool()
def skill_12_repair_log_entry_validation(
    current_a: float = 45.2,
    pressure_mpa: float = 2.1,
    equipment_id: Optional[str] = None,
    repair_datetime: Optional[str] = None,
    error_code: Optional[str] = None,
    description: Optional[str] = None
) -> str:
    """
    維修履歷欄位防呆驗證工具 (Skill 12)：
    以正則表達式與臨界值檢查維修案例欄位（電流、壓力必填；設備 ID、維修時間、故障碼、處置說明選填），
    一次列出所有不合格欄位，並對常態範圍外的數值給出警告。
    """
    return _dump(validate_repair_log_entry(
        current_a=current_a, pressure_mpa=pressure_mpa, equipment_id=equipment_id,
        repair_datetime=repair_datetime, error_code=error_code, description=description
    ))


@mcp.tool()
def skill_13_error_code_perceptron_check(
    current_a: float = 45.2,
    pressure_mpa: float = 2.1,
    confirmed_label: Optional[int] = None
) -> str:
    """
    單層感知器即時合規驗證工具 (Skill 13)：
    以單層感知器對電流與壓力做二元判定（0=合規、1=異常）；
    若提供人工確認結果 confirmed_label（0 或 1）且與預測不符，會依 w ← w + η(y-ŷ)z 更新權重並保存。
    """
    return _dump(check_error_code_perceptron(
        features=[current_a, pressure_mpa], confirmed_label=confirmed_label
    ))


@mcp.tool()
def skill_14_yield_rate_anomaly_detection(
    temp: float = 180.5,
    cooling: float = 42.0,
    speed: float = 15.2,
    n_trees: int = 100
) -> str:
    """
    良率預測與品質異常偵測工具 (Skill 14)：
    以隨機森林（Bootstrap 多棵 CART 決策樹 + 多數決）預測批次的良品機率與品質異常標籤
    （0 正常 / 1 異常），回傳 OOB 與測試集準確率、投票數與演算法推導步驟。
    加熱溫度 temp (°C)、冷卻水流量 cooling (L/min)、軋延速度 speed (m/min)。
    """
    return _dump(detect_yield_anomaly(batch_params=[temp, cooling, speed], n_trees=n_trees))


@mcp.tool()
def skill_15_feature_importance_ranking(batch_id: Optional[str] = "B-2026-10", n_trees: int = 100) -> str:
    """
    特徵重要度排序工具 (Skill 15)：
    計算隨機森林各製程特徵的吉尼不純度平均下降量 (MDI) 並排序，
    同時以測試集排列重要度交叉檢查，回傳排名、重要度與跨樹標準差。
    """
    return _dump(rank_feature_importance(batch_id=batch_id, n_trees=n_trees))


@mcp.tool()
def skill_16_root_cause_attribution_report(batch_id: Optional[str] = "B-2026-10", n_trees: int = 100) -> str:
    """
    品質異常根因歸因報告工具 (Skill 16)：
    整合隨機森林預測與 MDI 重要度，以「重要度 × 批次偏離良品基準的程度」歸因，
    回傳根因特徵、風險分數、處置建議與各參數歸因占比（相關性啟發式，非因果證明）。
    """
    return _dump(build_root_cause_report(batch_id=batch_id, n_trees=n_trees))


@mcp.tool()
def skill_17_steel_surface_defect_classify(
    area: float = 150,
    aspect_ratio: float = 4.2,
    contrast: float = 85
) -> str:
    """
    鋼板表面缺陷分類工具 (Skill 17)：
    以 CART 決策樹（吉尼不純度切分）對缺陷面積 (mm²)、長寬比、灰階對比度做多類別分類，
    回傳缺陷類別、決策路徑、葉節點純度與測試集混淆矩陣。
    """
    return _dump(classify_steel_defect(area=area, aspect_ratio=aspect_ratio, contrast=contrast))


@mcp.tool()
def skill_18_defect_geometric_feature_eval(model_id: str = "CART_DEFECT_V1") -> str:
    """
    缺陷特徵影響力評估工具 (Skill 18)：
    由決策樹各節點的吉尼下降量計算面積、長寬比、對比度的影響力，
    並以測試集排列重要度交叉檢查（描述模型如何使用特徵，不代表物理因果）。
    """
    return _dump(evaluate_defect_features(model_id=model_id))


@mcp.tool()
def skill_19_decision_tree_rule_extraction(
    alpha_threshold: float = 0.01,
    area: Optional[float] = None,
    aspect_ratio: Optional[float] = None,
    contrast: Optional[float] = None,
    auto_alpha: bool = False
) -> str:
    """
    決策樹剪枝與白盒規則導出工具 (Skill 19)：
    以代價複雜度剪枝 R_α(T)=R(T)+α|T| 縮減決策樹（驗證集建議 α、測試集報告剪枝前後準確率），
    並把每條根到葉的路徑轉成 IF-THEN 規則；若提供缺陷特徵則標出符合的規則。
    """
    return _dump(extract_decision_tree_rules(
        alpha_threshold=alpha_threshold, area=area, aspect_ratio=aspect_ratio,
        contrast=contrast, auto_alpha=auto_alpha
    ))


def _spc_zscores(columns=("temp", "pressure")):
    """MCP 工具未提供資料時，使用與網頁相同的製程資料（data/process_params.csv 或示範資料）。"""
    rows, source = spc_load_data()
    Z, _ = spc_standardize(rows, list(columns))
    return rows, Z, source


@mcp.tool()
def skill_20_process_parameter_kmeans(k: int = 3, z_scores: Optional[List[List[float]]] = None) -> str:
    """
    製程參數 K-Means 分群工具 (Skill 20)：
    對標準化後的溫度、壓力做 K-Means（k-means++ 多起點取最小 SSE），回傳各群中心、大小、SSE、輪廓係數。
    未提供 z_scores 時使用系統的製程資料（無 CSV 則為示範用合成資料）。
    """
    if z_scores is None:
        _, z_scores, _ = _spc_zscores()
    return _dump(run_kmeans(z_scores=z_scores, k=k))


@mcp.tool()
def skill_21_elbow_method_optimal_k(max_k: int = 8, z_scores: Optional[List[List[float]]] = None) -> str:
    """
    手肘法最佳群數工具 (Skill 21)：
    計算 K=1..max_k 的 SSE，以弦距法找手肘，並用輪廓係數交叉檢查（手肘明顯不代表資料真有群結構）。
    未提供 z_scores 時使用系統的製程資料。
    """
    if z_scores is None:
        _, z_scores, _ = _spc_zscores()
    return _dump(find_optimal_k(data=z_scores, max_k=max_k))


@mcp.tool()
def skill_22_spc_control_limit_monitoring(
    data_series: Optional[List[float]] = None,
    baseline_n: Optional[int] = None,
    feature: str = "temp",
    use_zscore: bool = True
) -> str:
    """
    SPC 管制界限與異常點監控工具 (Skill 22)：
    UCL/LCL = 平均 ± 3σ，標出超界點，並附 I-MR 穩健 σ 與連續 8 點同側檢查。
    未提供 data_series 時使用系統製程資料的 feature（temp 或 pressure）；
    use_zscore=True 時先標準化（限界必然為 ±3，請搭配 baseline_n 使用較有意義）。
    """
    if data_series is None:
        if feature not in ("temp", "pressure"):
            return _dump({"found": False, "answer_text": "feature 需為 temp 或 pressure", "steps": []})
        rows, source = spc_load_data()
        if use_zscore:
            zs, _ = spc_standardize(rows, [feature])
            data_series = [r[0] for r in zs]
        else:
            data_series = [r[feature] for r in rows]
    return _dump(monitor_spc(data_series=data_series, baseline_n=baseline_n))


@mcp.tool()
def skill_23_ipi_mlp_forecast(
    historical_ipi: Optional[List[float]] = None,
    export_orders: Optional[List[float]] = None,
    utilization: Optional[List[float]] = None,
    start_month: Optional[int] = None,
    epochs: int = 500,
    learning_rate: float = 0.05,
    hidden_units: int = 6
) -> str:
    """
    工業生產指數 MLP 預測工具 (Skill 23)：
    真實訓練單隱藏層 MLP（反向傳播），依時間切分訓練／測試，預測未來三個月 IPI，並與「延續上月」基準比較。
    未提供 historical_ipi 時使用系統的月度資料（無 CSV 則為示範用合成資料）。至少需要 60 個月。結果僅供參考。
    """
    return _dump(forecast_ipi_mlp(historical_ipi=historical_ipi, export_orders=export_orders, utilization=utilization,
                                  start_month=start_month, epochs=epochs, learning_rate=learning_rate,
                                  hidden_units=hidden_units))


def _equipment_matrix():
    rows, _ = equipment_load_data()
    Z, _ = equipment_risk_matrix(rows, ["failure_rate", "mtbf_hours", "load_pct"])
    return rows, Z


@mcp.tool()
def skill_24_preventive_maintenance_hierarchy(
    equipment_risk_matrix: Optional[List[List[float]]] = None,
    linkage: str = "average",
    equipment_ids: Optional[List[str]] = None
) -> str:
    """
    設備風險凝聚階層式分群工具 (Skill 24)：
    依設備風險指標（建議為風險方向一致的 z 分數）建歐氏距離矩陣，以凝聚法建階層樹（single/complete/average）。
    未提供矩陣時使用系統的設備風險資料（故障率、MTBF、運轉負載）。
    """
    if equipment_risk_matrix is None:
        rows, equipment_risk_matrix = _equipment_matrix()
        equipment_ids = equipment_ids or [r["equipment_id"] for r in rows]
    return _dump(build_hierarchy(equipment_risk_matrix, linkage, equipment_ids))


@mcp.tool()
def skill_25_factory_risk_dendrogram_eval(
    distance_threshold: Optional[float] = None,
    linkage: str = "average",
    capacity_per_week: int = 3
) -> str:
    """
    樹狀圖切割與預防維護排程工具 (Skill 25)：
    以系統設備風險資料建樹（skill_24），依距離門檻切割成風險階層（未提供門檻則自動建議），
    輸出各群設備、相對風險層級、預防維護週次與風險摘要。風險層級是相對排名，非絕對危險程度。
    """
    rows, Z = _equipment_matrix()
    tree = build_hierarchy(Z, linkage, [r["equipment_id"] for r in rows])
    return _dump(evaluate_dendrogram(distance_threshold=distance_threshold, hierarchy=tree,
                                     equipment_rows=rows, capacity_per_week=capacity_per_week))


@mcp.tool()
def skill_26_document_catalog_query(
    categories: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 20
) -> str:
    """
    文件目錄查詢工具 (Skill 26)：
    依類別、更新日期區間（YYYY-MM-DD）與關鍵字，查詢已收錄文件的名稱、更新日期、授權、內容預覽與出處。
    本工具只回傳「已公開」的文件；內部文件需在啟動 MCP 伺服器時設定環境變數 MANUFACTURING_KB_MCP_INTERNAL=1 才會納入。
    """
    role = "internal" if os.environ.get("MANUFACTURING_KB_MCP_INTERNAL") == "1" else "public"
    return _dump(query_document_catalog(role=role, categories=categories, start_date=start_date, end_date=end_date,
                                        keyword=keyword, limit=limit))


@mcp.tool()
def skill_27_kb_import_pipeline(
    files: List[str],
    file_type: str = "設備規格書",
    chunk_size: int = 500,
    overlap: int = 50,
    strip_noise: bool = True,
    normalize_datetime: bool = True,
    dedupe: bool = True,
    dry_run: bool = True
) -> str:
    """
    知識庫檔案匯入整理工具 (Skill 27)：
    對已上傳到系統 data/uploads 的檔名（.pdf/.csv/.md）依序做：讀取檢查 → 正則清洗 → SHA-256 去重 →
    筆數核對 → 滑動視窗切片並寫入文件索引。預設 dry_run=True 只試跑、不寫入索引；
    實際匯入請把 dry_run 設為 False。匯入的文件預設為內部資料（非公開）。
    """
    rules = {"chunk_size": chunk_size, "overlap": overlap, "strip_noise": strip_noise,
             "normalize_datetime": normalize_datetime, "dedupe": dedupe}
    return _dump(import_kb_files(files=files, rules=rules, file_type=file_type, dry_run=dry_run))


@mcp.tool()
def skill_28_data_freshness_check(
    today: Optional[str] = None,
    max_lag_months: int = 3,
    decay_lambda: float = 0.1
) -> str:
    """
    資料新鮮度檢查工具 (Skill 28)：
    讀取各資料集最新日期（匯入文件、分析用 CSV、docs/ 檢索文件），依基準日（YYYY-MM-DD，預設今天）
    算落後月數與時間衰減權重 e^(-λ·Δt)，落後超過門檻（預設 3 個月）就提醒。
    每個資料集會標出日期可信度（資料內日期／檔案修改時間／無法判斷）。只檢查「有多舊」，不判斷法規是否已修訂。
    """
    return _dump(check_data_freshness(today=today, max_lag_months=max_lag_months, decay_lambda=decay_lambda))


@mcp.tool()
def skill_29_retrieval_quality_eval(top_k: int = 3, threshold: float = 0.10) -> str:
    """
    檢索品質評估工具 (Skill 29)：
    以 data/eval/gold_20.json 的標準問答逐題呼叫 skill_01，計算 Top-3 命中率、MRR（截斷於前 10 名）、
    第 1 名引用正確來源比例與錯誤案例（查無資料／偏離）。找不到題庫檔時會從 docs/ 自動產生題目，
    此時結果只代表系統接線正常，不代表真實提問的品質。
    """
    return _dump(evaluate_retrieval_quality(top_k=top_k, threshold=threshold))


if __name__ == "__main__":
    # 啟動 MCP 伺服器（透過標準輸入輸出 STDIO 與 AnythingLLM 通訊）
    mcp.run()
