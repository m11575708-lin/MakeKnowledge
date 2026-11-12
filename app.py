import hmac
import json
import importlib
import os
import re
import secrets
import sys
import threading
import traceback
from datetime import datetime

import requests
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

# 將專案根目錄加入系統路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)


# ---------------------------------------------------------------------------
# 安全匯入 Skill：優先 skills/ 資料夾，其次專案根目錄。
# 找不到或匯入失敗時，回傳一個會輸出錯誤 JSON 的備用函數，避免整個應用崩潰；
# 真正的錯誤原因會印到 stderr，方便排查。
# ---------------------------------------------------------------------------
def _safe_skill(module_name: str, func_name: str):
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
reset_perceptron_model = _safe_skill("skill_13_error_code_perceptron_check", "reset_perceptron_model")
save_repair_entry = _safe_skill("_repair_log_store", "save_repair_entry")
is_duplicate_entry = _safe_skill("_repair_log_store", "is_duplicate")
recent_repair_entries = _safe_skill("_repair_log_store", "recent_entries")
detect_yield_anomaly = _safe_skill("skill_14_yield_rate_anomaly_detection", "detect_yield_anomaly")
rank_feature_importance = _safe_skill("skill_15_feature_importance_ranking", "rank_feature_importance")
build_root_cause_report = _safe_skill("skill_16_root_cause_attribution_report", "build_root_cause_report")
load_quality_batches = _safe_skill("_quality_data", "load_batches")
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
ipi_load_data = _safe_skill("_ipi_data", "load_data")
import_kb_files = _safe_skill("skill_27_kb_import_pipeline", "import_kb_files")
publish_dataset = _safe_skill("_import_registry", "publish_dataset")
refresh_dataset = _safe_skill("_import_registry", "refresh_dataset")
detect_dataset = _safe_skill("_import_registry", "detect_dataset")
kb_recent_logs = _safe_skill("_kb_store", "recent_logs")
kb_totals = _safe_skill("_kb_store", "totals")
kb_log_publish = _safe_skill("_kb_store", "log_publish")
check_data_freshness = _safe_skill("skill_28_data_freshness_check", "check_data_freshness")
evaluate_retrieval_quality = _safe_skill("skill_29_retrieval_quality_eval", "evaluate_retrieval_quality")
catalog_retrieve = _safe_skill("_catalog", "retrieve_visible")
query_document_catalog = _safe_skill("skill_26_document_catalog_query", "query_document_catalog")
get_document_preview = _safe_skill("skill_26_document_catalog_query", "get_document_preview")
read_csv_file = _safe_skill("_doc_readers", "read_csv")
decode_text_bytes = _safe_skill("_doc_readers", "decode_text")
equipment_load_data = _safe_skill("_equipment_data", "load_data")
equipment_risk_matrix = _safe_skill("_equipment_data", "risk_matrix")

# static_folder=None：避免 Flask 預設的 /static 路由把整個專案目錄（含 app.py 原始碼）公開出去
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024      # 單次上傳請求上限 32MB（單檔上限 5MB 另外檢查）


@app.errorhandler(RequestEntityTooLarge)
def _too_large(_e):
    return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "上傳內容過大（單次請求上限 32MB、單檔上限 5MB）"}), 413

# AnythingLLM 設定（金鑰請以環境變數提供，不要寫在程式碼裡）
#   Windows PowerShell:  $env:ANYTHINGLLM_API_KEY="你的新金鑰"
#   macOS / Linux:       export ANYTHINGLLM_API_KEY="你的新金鑰"
ANYTHINGLLM_API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "")
BASE_URL = os.environ.get("ANYTHINGLLM_BASE_URL", "http://127.0.0.1:3001")
WORKSPACE_SLUG = os.environ.get("ANYTHINGLLM_WORKSPACE", "manufacturingknowledge")

# 允許對外提供的非 HTML 靜態檔（白名單）
ALLOWED_STATIC_FILES = {"nav.js"}


# 1. 首頁
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "page01_knowledge_chat.html")


# 2. 提供 .html 頁面與白名單內的共用腳本（nav.js）
@app.route("/<path:filename>")
def serve_static_pages(filename):
    if filename.endswith(".html") or filename in ALLOWED_STATIC_FILES:
        return send_from_directory(BASE_DIR, filename)
    return "Not Found", 404


# ---------------------------------------------------------------------------
# 文件可見性（公開／內部）：規則集中在 skills/_catalog.py，預設「不公開」。
#   * 民眾頁（page05）永遠只看公開文件；page01／page02 依權杖決定：
#     - 伺服器沒設任何權杖（本機開發模式）：沒指定 view 時視為內部
#     - 伺服器有設權杖：帶有效 X-Import-Token（管理者／工程師／廠長）才是內部，否則為公開；權杖錯誤回 401
#   * 前端可以主動要求 view="public"（縮小權限永遠允許）；要求 "internal" 但沒有有效權杖回 401。
# ---------------------------------------------------------------------------
def _internal_auth():
    """回傳 (通過, 伺服器是否要求權杖, 是否提供了無效權杖)。"""
    toks = [os.environ.get(k, "") for k in ("IMPORT_ADMIN_TOKEN", "IMPORT_UPLOAD_TOKEN", "OPS_VIEW_TOKEN")]
    if not any(toks):
        return True, False, False
    given = request.headers.get("X-Import-Token", "")
    if not given:
        return False, True, False
    if any(t and hmac.compare_digest(given.encode(), t.encode()) for t in toks):
        return True, True, False
    return False, True, True


def _catalog_view(requested):
    """回傳 (view, 錯誤回應)。view 為 'public' 或 'internal'。"""
    if requested not in (None, "public", "internal"):
        return None, (jsonify({"status": "error", "found": False, "steps": [], "answer_text": "view 只能是 public 或 internal"}), 400)
    if requested == "public":
        return "public", None
    ok, _required, bad = _internal_auth()
    if ok:
        return "internal", None
    if bad or requested == "internal":
        return None, (jsonify({"status": "error", "found": False, "steps": [], "answer_text": "未授權：內部文件需要有效的 X-Import-Token"}), 401)
    return "public", None


def _bad_request(msg):
    return jsonify({"status": "error", "found": False, "steps": [], "answer_text": msg}), 400


def _json_body():
    data = request.get_json(silent=True)
    if data is None and request.data:
        return None, _bad_request("請求內容不是有效的 JSON")
    if data is not None and not isinstance(data, dict):
        return None, _bad_request("請求內容必須是 JSON 物件")
    return data or {}, None


def _num_in(data, key, default, lo, hi, integer=False):
    v = data.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi) or (integer and not isinstance(v, int)):
        return None
    return v


ANYTHINGLLM_PUBLIC_WORKSPACE = os.environ.get("ANYTHINGLLM_PUBLIC_WORKSPACE", "manufacturing-regulations")


# 3. 即時智慧問答 API（US-16 / page01）：skill_01 檢索與 Guardrail → 通過才呼叫 AnythingLLM 產生回答
@app.route("/api/search", methods=["POST"])
def api_search():
    data, err = _json_body()
    if err:
        return err
    query_text = data.get("query", "") or data.get("message", "")
    if not isinstance(query_text, str) or len(query_text) > 500:
        return _bad_request("查詢內容必須是 500 字以內的字串")
    scope = data.get("scope", "all")
    if scope not in ("all", "regulations", "repairs"):
        return _bad_request("scope 只能是 all、regulations 或 repairs")
    threshold = _num_in(data, "threshold", 0.10, 0, 1)
    if threshold is None:
        return _bad_request("threshold 必須是 0–1 的數值")
    view, err = _catalog_view(data.get("view"))
    if err:
        return err

    if not query_text.strip():
        return jsonify({"status": "success", "found": False, "query": "",
                        "answer_text": "請在檢索框輸入您想查詢的製造規範、SOP 或法規關鍵字。",
                        "source_title": "等待輸入", "source_url": "", "search_results": [], "steps": []})

    try:
        r = catalog_retrieve(query_text=query_text, scope=scope, view=view, top_k=3, threshold=threshold,
                             save_path=os.path.join(BASE_DIR, "data", "tool_regulation_search_result.json"))
    except Exception as e:
        print(f"[search 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"檢索發生錯誤：{str(e)}", "steps": []}), 500
    if r.get("status") == "error":
        return jsonify({"status": "error", "found": False, "query": query_text, "answer_text": r.get("answer_text"), "steps": []}), 500

    steps = list(r["steps"])
    sources = [{k: v for k, v in x.items() if k != "content"} for x in r["search_results"]]
    base = {"status": "success", "query": query_text, "scope": scope, "view": view, "data_source": "docs/（skill_01 檢索）",
            "similarity_score": r["similarity_score"], "threshold": threshold, "guardrail_status": r["guardrail_status"]}

    def llm_step(desc):
        return {"step_number": len(steps) + 1, "step_name": "AnythingLLM 產生回答", "description": desc,
                "skill_name": "anythingllm_developer_api", "algorithm_used": "Grounded Generation (mode: query)", "package_used": "requests"}

    if not r["found"]:
        steps.append(llm_step("未呼叫 AnythingLLM：Guardrail 判定查無足夠相符的資料，不產生回答以避免幻覺。"))
        return jsonify({**base, "found": False, "answer_text": r["answer_text"], "answer_source": None, "llm_used": False,
                        "source_title": "無引用來源", "source_url": "", "search_results": [], "steps": steps})

    answer_text, answer_source, llm_used, note = r["answer_text"], "skill_01_extract", False, None
    if not ANYTHINGLLM_API_KEY:
        note = "尚未設定環境變數 ANYTHINGLLM_API_KEY，以下為 skill_01 檢索到的條文原文（未經 LLM 整理）。"
    else:
        mapping = {"all": WORKSPACE_SLUG, "regulations": "manufacturing-regulations", "repairs": "manufacturing-repairs"}
        slug = ANYTHINGLLM_PUBLIC_WORKSPACE if view == "public" else mapping[scope]
        try:
            resp = requests.post(f"{BASE_URL}/api/v1/workspace/{slug}/chat",
                                 json={"message": query_text, "mode": "query"},
                                 headers={"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}", "Content-Type": "application/json"},
                                 timeout=(5, 120))
            text = (resp.json().get("textResponse") or "").strip() if resp.status_code == 200 else ""
            if text:
                answer_text, answer_source, llm_used = text, "anythingllm", True
            else:
                note = f"AnythingLLM 沒有產生回答（狀態碼 {resp.status_code}），改顯示 skill_01 檢索到的條文原文。"
        except requests.exceptions.Timeout:
            note = "連線至 AnythingLLM 逾時，改顯示 skill_01 檢索到的條文原文。"
        except (requests.exceptions.RequestException, ValueError):
            note = "無法連線至 AnythingLLM，改顯示 skill_01 檢索到的條文原文。"
        slug_txt = f"工作區 '{slug}'"
    steps.append(llm_step(
        (f"Guardrail 通過後呼叫 AnythingLLM {slug_txt}（mode: query，只依文件回答）產生回答。" if llm_used else f"未使用 LLM 回答：{note}")))
    return jsonify({**base, "found": True, "answer_text": answer_text, "answer_source": answer_source, "llm_used": llm_used,
                    "llm_note": note, "source_title": r["source_title"], "source_url": r["source_url"],
                    "search_results": sources, "steps": steps})


# 4. 文件收錄頁（US-17 / page02）：skill_26 以 sqlite3 依角色、類別、日期、關鍵字過濾文件元資料
@app.route("/api/documents", methods=["POST"])
def api_documents():
    data, err = _json_body()
    if err:
        return err
    view, err = _catalog_view(data.get("view"))
    if err:
        return err
    categories = data.get("categories")
    legacy = data.get("category")
    if categories is None and isinstance(legacy, str) and legacy not in ("", "all"):
        categories = [legacy]
    keyword = data.get("keyword", data.get("query"))
    try:
        r = query_document_catalog(role="public" if view == "public" else "internal", categories=categories,
                                   start_date=data.get("start_date") or None, end_date=data.get("end_date") or None,
                                   keyword=keyword, limit=data.get("limit", 50), offset=data.get("offset", 0))
    except Exception as e:
        print(f"[documents 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "documents": [], "answer_text": f"文件目錄查詢發生錯誤：{str(e)}", "steps": []}), 500
    return jsonify({**{k: v for k, v in r.items() if k != "steps"}, "view": view, "steps": r.get("steps", [])})


@app.route("/api/documents/preview", methods=["POST"])
def api_documents_preview():
    data, err = _json_body()
    if err:
        return err
    view, err = _catalog_view(data.get("view"))
    if err:
        return err
    r = get_document_preview(data.get("doc_id"), role="public" if view == "public" else "internal")
    return jsonify({**r, "view": view, "steps": []})


# 5. 公開法規與機械操作資格查詢 API（US-01、US-02 / page05）——民眾頁，只查公開文件
@app.route("/api/regulation-search", methods=["POST"])
def api_regulation_search():
    data, err = _json_body()
    if err:
        return err
    query_text = data.get("query")
    if not isinstance(query_text, str) or not 1 <= len(query_text.strip()) <= 200:
        return _bad_request("請輸入 1–200 字的關鍵字")
    types = data.get("types", [])
    if not isinstance(types, list) or len(types) > 10 or not all(isinstance(t, str) and 0 < len(t) <= 40 for t in types):
        return _bad_request("types 必須是最多 10 個字串的清單")
    top_k = _num_in(data, "top_k", 3, 1, 10, integer=True)
    threshold = _num_in(data, "threshold", 0.10, 0, 1)
    if top_k is None or threshold is None:
        return _bad_request("top_k 必須是 1–10 的整數、threshold 必須是 0–1 的數值")
    try:
        r = catalog_retrieve(query_text=query_text.strip(), scope="all", view="public", top_k=top_k, threshold=threshold, types=types,
                             save_path=os.path.join(BASE_DIR, "data", "regulation_search_result.json"))
    except Exception as e:
        print(f"[regulation-search 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"法規檢索發生錯誤：{str(e)}", "steps": []}), 500
    if r.get("status") == "error":
        return jsonify({"status": "error", "found": False, "answer_text": r.get("answer_text"), "steps": []}), 500
    results = [{k: x[k] for k in ("regulation_id", "title", "summary", "content", "category", "similarity_score", "source_url", "license_type")}
               for x in r["search_results"]]
    note = None
    if r["n_searchable"] == 0:
        note = "目前沒有任何公開文件可檢索。管理者需在 data/catalog_manifest.json 把確定可公開的文件標為 is_public: true。"
    return jsonify({"status": "success", "found": r["found"], "query": r["query"], "results": results, "threshold": threshold,
                    "n_searchable": r["n_searchable"], "guardrail_status": r["guardrail_status"], "answer_text": note or r["answer_text"],
                    "steps": r["steps"]})


@app.route("/api/qualification-match", methods=["POST"])
def api_qualification_match():
    data, err = _json_body()
    if err:
        return err
    equipment_type = data.get("equipment_type")
    if not isinstance(equipment_type, str) or not 1 <= len(equipment_type.strip()) <= 40:
        return _bad_request("equipment_type 必須是 1–40 字的字串")
    creds = data.get("user_credentials", [])
    if not isinstance(creds, list) or len(creds) > 20 or not all(isinstance(c, str) and len(c) <= 60 for c in creds):
        return _bad_request("user_credentials 必須是最多 20 個、每個 60 字以內的字串清單")
    query_text = data.get("query", "")
    if not isinstance(query_text, str) or len(query_text) > 200:
        return _bad_request("query 必須是 200 字以內的字串")
    top_k = _num_in(data, "top_k", 3, 1, 10, integer=True)
    threshold = _num_in(data, "threshold", 0.20, 0, 1)
    if top_k is None or threshold is None:
        return _bad_request("top_k 必須是 1–10 的整數、threshold 必須是 0–1 的數值")
    try:
        result = match_machine_qualification(equipment_type=equipment_type.strip(), user_credentials=creds,
                                             query_text=query_text.strip(), top_k=top_k, threshold=threshold)
        return jsonify(result)
    except Exception as e:
        print(f"[qualification-match 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"機械資格比對運算發生錯誤：{str(e)}", "steps": []}), 500


# 6. 設備壽命預測 API（US-03 / page06）：依序串接 skill_03 -> skill_04 -> skill_05
RUL_DEFAULTS = {"operating_hours": 1500, "vibration": 2.8, "temperature": 75, "load_rate": 85}


def _merge_steps(*results):
    """把多個 Skill 的 steps 合併並重新編號，保留各自的 skill_name 標籤。"""
    merged = []
    for res in results:
        for step in (res or {}).get("steps", []):
            merged.append({**step, "step_number": len(merged) + 1})
    return merged


@app.route("/api/rul-predict", methods=["POST"])
def api_rul_predict():
    data = request.get_json(silent=True) or {}

    values = {}
    for key, default in RUL_DEFAULTS.items():
        raw = data.get(key, default)
        try:
            values[key] = float(raw)
        except (TypeError, ValueError):
            return jsonify({
                "status": "error",
                "found": False,
                "answer_text": f"欄位 {key} 必須為數值，收到：{raw!r}",
                "steps": [],
            }), 400

    try:
        preprocessing = preprocess_sensor_data(raw_values=values)
        prediction = predict_equipment_rul(**values)
        attribution = attribute_degradation_features(**values)
    except Exception as e:
        print(f"[rul-predict 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({
            "status": "error",
            "found": False,
            "answer_text": f"壽命預測運算發生錯誤：{str(e)}",
            "steps": [],
        }), 500

    return jsonify({
        "status": "success",
        "found": bool(prediction.get("found")),
        "equipment_id": str(data.get("equipment_id", "")),
        "preprocessing": preprocessing,
        "prediction": prediction,
        "attribution": attribution,
        "steps": _merge_steps(preprocessing, prediction, attribution),
    })


# 7. 設備突發故障風險評估 API（US-04 / US-05 / page07）：依序串接 skill_06 -> skill_07 -> skill_08
FAILURE_DEFAULTS = {"recency_days": 45, "alarms_90d": 12, "pressure": 1.8}
COST_DEFAULTS = {"cost_downtime": 50000, "cost_inspection": 2000}


@app.route("/api/failure-risk", methods=["POST"])
def api_failure_risk():
    data = request.get_json(silent=True) or {}

    values = {}
    for key, default in {**FAILURE_DEFAULTS, **COST_DEFAULTS}.items():
        raw = data.get(key, default)
        try:
            values[key] = float(raw)
        except (TypeError, ValueError):
            return jsonify({
                "status": "error",
                "found": False,
                "answer_text": f"欄位 {key} 必須為數值，收到：{raw!r}",
                "steps": [],
            }), 400

    try:
        probability = calculate_failure_probability(
            recency_days=values["recency_days"],
            alarms_90d=values["alarms_90d"],
            pressure=values["pressure"],
        )
        prob_value = probability.get("failure_probability")
        risk = classify_risk_level(failure_probability=prob_value)
        cost = tune_cost_threshold(
            cost_downtime=values["cost_downtime"],
            cost_inspection=values["cost_inspection"],
            failure_probability=prob_value,
        )
    except Exception as e:
        print(f"[failure-risk 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({
            "status": "error",
            "found": False,
            "answer_text": f"故障風險運算發生錯誤：{str(e)}",
            "steps": [],
        }), 500

    return jsonify({
        "status": "success",
        "found": bool(probability.get("found")),
        "equipment_id": str(data.get("equipment_id", "")),
        "probability": probability,
        "risk": risk,
        "cost": cost,
        "steps": _merge_steps(probability, risk, cost),
    })


# 8. 歷史維修案例檢索與備品推薦 API（US-06 / US-07 / page08）
#    資料流：skill_10（依故障碼校正特徵權重）-> skill_09（KNN 檢索）-> skill_11（Item-CF 備品推薦）
CASE_FEATURE_DEFAULTS = {"vibration": 2.8, "temperature": 75.0, "pressure": 1.8}
CASE_FEATURE_ORDER = ["vibration", "temperature", "pressure"]


@app.route("/api/case-retrieval", methods=["POST"])
def api_case_retrieval():
    data = request.get_json(silent=True) or {}
    error_code = str(data.get("error_code", "E-8021"))
    restrict = data.get("restrict_to_error_code", False) is True

    values, multipliers = [], []
    for key in CASE_FEATURE_ORDER:
        for target, field, default in ((values, key, CASE_FEATURE_DEFAULTS[key]), (multipliers, f"w_{key}", 1.0)):
            raw = data.get(field, default)
            try:
                target.append(float(raw))
            except (TypeError, ValueError):
                return jsonify({
                    "status": "error",
                    "found": False,
                    "answer_text": f"欄位 {field} 必須為數值，收到：{raw!r}",
                    "steps": [],
                }), 400

    try:
        pattern = match_error_code_pattern(error_code=error_code, feature_vector=values)
        calibrated = pattern.get("feature_weights") if pattern.get("found") else None
        weights = ([c * m for c, m in zip(calibrated, multipliers)] if calibrated else multipliers)

        cases = search_similar_repair_cases(
            feature_vector=values,
            top_k=3,
            weights=weights,
            error_code=error_code if pattern.get("found") else None,
            restrict_to_error_code=restrict and bool(pattern.get("found")),
        )
        neighbors = [{"case_id": c["case_id"], "similarity": c["similarity"]}
                     for c in cases.get("top3_similar_cases", [])] or None
        parts = recommend_spare_parts(neighbors=neighbors)
    except Exception as e:
        print(f"[case-retrieval 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({
            "status": "error",
            "found": False,
            "answer_text": f"案例檢索運算發生錯誤：{str(e)}",
            "steps": [],
        }), 500

    return jsonify({
        "status": "success",
        "found": bool(cases.get("found")),
        "pattern": pattern,
        "cases": cases,
        "parts": parts,
        "steps": _merge_steps(pattern, cases, parts),
    })


# 9. 維修案例登錄與故障碼驗證 API（US-08 / page09）：skill_12 欄位驗證 -> skill_13 感知器合規判定
@app.route("/api/repair-log", methods=["POST"])
def api_repair_log():
    data = request.get_json(silent=True) or {}
    save = data.get("save", False) is True
    confirmed = data.get("confirmed_label")
    if confirmed is not None and (isinstance(confirmed, bool) or confirmed not in (0, 1)):
        return jsonify({"status": "error", "found": False,
                        "answer_text": "confirmed_label 只能是 0、1 或不提供", "steps": []}), 400

    def num(key):
        v = data.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v
        try:
            return float(v)
        except (TypeError, ValueError):
            return str(v)   # 交給 skill_12 回報「必須為數值」

    try:
        validation = validate_repair_log_entry(
            current_a=num("current_a"), pressure_mpa=num("pressure_mpa"),
            equipment_id=data.get("equipment_id") or None,
            repair_datetime=data.get("repair_datetime") or None,
            error_code=data.get("error_code") or None,
            description=data.get("description") or None)
        perceptron, storage = None, {"requested": save, "saved": False, "duplicate": False,
                                     "entry_id": None, "message": "尚未儲存"}
        if validation.get("is_valid"):
            entry = validation["normalized_entry"]
            duplicate = save and is_duplicate_entry(entry) is True
            # 重複案例不再拿來訓練感知器，避免連點按鈕造成權重被重複更新
            perceptron = check_error_code_perceptron(
                features=[entry["current_a"], entry["pressure_mpa"]],
                confirmed_label=None if duplicate else confirmed)
            if save:
                verdict = {"status_label": perceptron.get("status_label"),
                           "guardrail_status": perceptron.get("guardrail_status")}
                has_full = all(k in entry for k in ("equipment_id", "repair_datetime", "error_code", "description"))
                if not has_full:
                    storage.update(message="儲存需要完整填寫設備 ID、維修時間、故障碼與處置說明，本次只做驗證。")
                else:
                    storage.update(save_repair_entry(entry, verdict))
        elif save:
            storage["message"] = "欄位驗證未通過，未儲存。"
    except Exception as e:
        print(f"[repair-log 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False,
                        "answer_text": f"維修案例驗證運算發生錯誤：{str(e)}", "steps": []}), 500

    return jsonify({
        "status": "success",
        "found": bool(validation.get("is_valid")),
        "validation": validation,
        "perceptron": perceptron,
        "storage": storage,
        "steps": _merge_steps(validation, perceptron),
    })


@app.route("/api/repair-log/recent", methods=["GET"])
def api_repair_log_recent():
    try:
        limit = int(request.args.get("limit", 8))
    except ValueError:
        limit = 8
    return jsonify({"status": "success", "entries": recent_repair_entries(limit)})


@app.route("/api/repair-log/reset-model", methods=["POST"])
def api_repair_log_reset_model():
    try:
        return jsonify(reset_perceptron_model())
    except Exception as e:
        print(f"[reset-model 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"重設失敗：{e}", "steps": []}), 500


# 10. 品質異常根本原因分析 API（US-09 / page10）：skill_14 隨機森林預測 -> skill_15 MDI 排序 -> skill_16 根因報告
@app.route("/api/root-cause/batches", methods=["GET"])
def api_root_cause_batches():
    try:
        batches, source = load_quality_batches()
    except Exception as e:
        print(f"[root-cause/batches 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "batches": [], "answer_text": f"無法載入批次資料：{e}"}), 500
    return jsonify({"status": "success", "batches": batches, "data_source": source})


@app.route("/api/root-cause", methods=["POST"])
def api_root_cause():
    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id") or None
    n_trees = data.get("n_trees", 100)
    params = data.get("batch_params")
    if params is not None and not isinstance(params, list):
        return jsonify({"status": "error", "found": False, "answer_text": "batch_params 必須是陣列 [temp, cooling, speed]",
                        "steps": []}), 400
    try:
        prediction = detect_yield_anomaly(batch_params=params, batch_id=batch_id if params is None else None, n_trees=n_trees)
        importance = rank_feature_importance(batch_id=batch_id, n_trees=n_trees)
        report = build_root_cause_report(batch_id=batch_id, batch_params=params, n_trees=n_trees,
                                         prediction=prediction, importance=importance)
    except Exception as e:
        print(f"[root-cause 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False,
                        "answer_text": f"根因分析運算發生錯誤：{str(e)}", "steps": []}), 500
    return jsonify({
        "status": "success",
        "found": bool(prediction.get("found")),
        "prediction": prediction,
        "importance": importance,
        "report": report,
        "steps": _merge_steps(prediction, importance, report),
    })


# 11. 鋼板表面缺陷分類與特徵評估 API（US-10 / US-11 / page11）：skill_17 CART 分類 -> skill_18 特徵影響力 -> skill_19 剪枝與規則
STEEL_DEFAULTS = {"area": 150, "aspect_ratio": 4.2, "contrast": 85}


@app.route("/api/steel-defects", methods=["POST"])
def api_steel_defects():
    data = request.get_json(silent=True) or {}

    def num(key, default):
        v = data.get(key, default)
        if isinstance(v, bool) or v is None:
            return v
        if isinstance(v, (int, float)):
            return v
        try:
            return float(v)
        except (TypeError, ValueError):
            return str(v)   # 交給 Skill 回報「必須為數值」

    area = num("area", STEEL_DEFAULTS["area"])
    ratio = num("aspect_ratio", STEEL_DEFAULTS["aspect_ratio"])
    contrast = num("contrast", STEEL_DEFAULTS["contrast"])
    alpha = num("alpha", 0.01)
    auto_alpha = data.get("auto_alpha", False) is True
    try:
        prediction = classify_steel_defect(area=area, aspect_ratio=ratio, contrast=contrast)
        importance = evaluate_defect_features()
        pruning = extract_decision_tree_rules(alpha_threshold=alpha, area=area, aspect_ratio=ratio,
                                              contrast=contrast, auto_alpha=auto_alpha)
    except Exception as e:
        print(f"[steel-defects 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False,
                        "answer_text": f"缺陷分類運算發生錯誤：{str(e)}", "steps": []}), 500
    return jsonify({
        "status": "success",
        "found": bool(prediction.get("found")),
        "prediction": prediction,
        "importance": importance,
        "pruning": pruning,
        "steps": _merge_steps(prediction, importance, pruning),
    })


@app.route("/api/spc-clustering", methods=["POST"])
def api_spc_clustering():
    """page12：skill_21（手肘法）→ skill_20（K-Means）→ skill_22（SPC，可關閉）。"""
    data = request.get_json(silent=True) or {}
    Z_TO_COL = {"temp_z": "temp", "press_z": "pressure"}
    feats = data.get("features", ["temp_z", "press_z"])
    if not isinstance(feats, list) or not feats or any(f not in Z_TO_COL for f in feats):
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "features 必須是 temp_z、press_z 的非空子集合"}), 400
    feats = [f for f in Z_TO_COL if f in feats]          # 去重並固定順序
    cols = [Z_TO_COL[f] for f in feats]

    def as_int(key, default, lo, hi):
        v = data.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return None
        return v

    k_mode = data.get("k_mode", "auto")
    max_k = as_int("max_k", 8, 3, 10)
    k_manual = as_int("k", 3, 1, 10)
    if k_mode not in ("auto", "manual") or max_k is None or k_manual is None:
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "k_mode 需為 auto/manual；max_k 需為 3–10 的整數；k 需為 1–10 的整數"}), 400
    spc_on = data.get("spc_enabled", True) is True
    spc_feature = data.get("spc_feature", "temp_z")
    spc_basis = data.get("spc_basis", "z")
    baseline_n = data.get("baseline_n")
    if spc_on and (spc_feature not in Z_TO_COL or spc_basis not in ("z", "raw")):
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "spc_feature 需為 temp_z/press_z；spc_basis 需為 z/raw"}), 400
    if baseline_n in ("", 0):
        baseline_n = None

    try:
        rows, source = spc_load_data()
        Z, stats = spc_standardize(rows, cols)
        elbow = find_optimal_k(data=Z, max_k=max_k)
        if k_mode == "auto":
            k_use = elbow.get("optimal_k") if elbow.get("found") else None
            km = run_kmeans(z_scores=Z, k=k_use) if k_use else {
                "found": False, "steps": [], "guardrail_status": "BLOCKED_BY_GUARDRAIL (upstream)",
                "answer_text": "手肘法被安全檢核攔截，無法自動決定 K；請改用手動 K"}
        else:
            k_use = k_manual
            km = run_kmeans(z_scores=Z, k=k_use)
        spc = None
        spc_series = None
        if spc_on:
            col = Z_TO_COL[spc_feature]
            if spc_basis == "z":
                zs, _ = spc_standardize(rows, [col])
                spc_series = [r[0] for r in zs]
            else:
                spc_series = [r[col] for r in rows]
            spc = monitor_spc(data_series=spc_series, baseline_n=baseline_n)
    except Exception as e:
        print(f"[spc-clustering 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False,
                        "answer_text": f"分群與 SPC 運算發生錯誤：{str(e)}", "steps": []}), 500

    centers_orig = None
    if km.get("found") and km.get("cluster_centers"):
        centers_orig = [[c[j] * stats[cols[j]]["std"] + stats[cols[j]]["mean"] for j in range(len(cols))]
                        for c in km["cluster_centers"]]
    out_set = set(spc.get("outlier_indices") or []) if spc and spc.get("found") else set()
    labels = km.get("labels") if km.get("found") else None
    points = [{"i": i, "z": [round(v, 4) for v in z], "label": (labels[i] if labels else None),
               "raw": [rows[i][c] for c in cols]} for i, z in enumerate(Z)]
    series_out = None
    if spc_series is not None:
        series_out = [{"i": i, "v": round(v, 4), "out": i in out_set} for i, v in enumerate(spc_series)]
    results = [elbow, km] + ([spc] if spc is not None else [])
    return jsonify({
        "status": "success",
        "found": bool(km.get("found")),
        "dataset": {"source": source, "n": len(rows), "features": feats, "columns": cols,
                    "stats": stats, "is_synthetic": source.startswith("synthetic")},
        "k_mode": k_mode, "k_used": k_use,
        "elbow": elbow, "kmeans": km, "spc": spc,
        "centers_original": centers_orig, "points": points,
        "spc_series": series_out, "spc_feature": spc_feature if spc_on else None, "spc_basis": spc_basis if spc_on else None,
        "steps": _merge_steps(*results),
    })


@app.route("/api/index-forecast", methods=["POST"])
def api_index_forecast():
    """page13：skill_23（IPI 的 MLP 預測）與 skill_24 → skill_25（設備風險階層與預防維護）。兩條鏈互相獨立。"""
    data = request.get_json(silent=True) or {}
    ALL_FEATS = ["ipi", "export", "util", "season"]
    ALL_IND = ["failure_rate", "mtbf_hours", "load_pct"]
    feats = data.get("features", ALL_FEATS)
    inds = data.get("indicators", ALL_IND)
    if not isinstance(feats, list) or not feats or any(f not in ALL_FEATS for f in feats):
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "features 必須是 ipi、export、util、season 的非空子集合"}), 400
    if not isinstance(inds, list) or not inds or any(i not in ALL_IND for i in inds):
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "indicators 必須是 failure_rate、mtbf_hours、load_pct 的非空子集合"}), 400
    feats = [f for f in ALL_FEATS if f in feats]
    inds = [i for i in ALL_IND if i in inds]

    def as_int(key, default, lo, hi):
        v = data.get(key, default)
        return v if (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi) else None

    def as_float(key, default, lo, hi, allow_none=False):
        v = data.get(key, default)
        if v is None and allow_none:
            return "auto"
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo < v <= hi:
            return None
        return float(v)

    epochs = as_int("epochs", 500, 10, 5000)
    hidden = as_int("hidden_units", 6, 2, 32)
    capacity = as_int("capacity_per_week", 3, 1, 20)
    lr = as_float("learning_rate", 0.05, 0.0, 1.0)
    thr = as_float("distance_threshold", None, 0.0, 1000.0, allow_none=True)
    linkage = data.get("linkage", "average")
    if None in (epochs, hidden, capacity, lr, thr) or linkage not in ("single", "complete", "average"):
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "epochs 需為 10–5000、hidden_units 2–32、capacity_per_week 1–20 的整數；learning_rate 需為 (0,1]；"
                                       "distance_threshold 需為正數或留空；linkage 需為 single/complete/average"}), 400
    thr = None if thr == "auto" else thr
    forecast_enabled = data.get("forecast_enabled", True) is True      # False：只重新切樹與排程，不重訓 MLP

    try:
        rows, ipi_source = ipi_load_data()
        forecast = forecast_ipi_mlp(features=feats, epochs=epochs, learning_rate=lr, hidden_units=hidden) \
            if forecast_enabled else None
        equip, equip_source = equipment_load_data()
        Z, ind_stats = equipment_risk_matrix(equip, inds)
        hierarchy = build_hierarchy(Z, linkage, [r["equipment_id"] for r in equip])
        dendro = evaluate_dendrogram(distance_threshold=thr, hierarchy=hierarchy, equipment_rows=equip,
                                     capacity_per_week=capacity) if hierarchy.get("found") else {
            "found": False, "steps": [], "guardrail_status": "BLOCKED_BY_GUARDRAIL (upstream)",
            "answer_text": "階層樹建立被安全檢核攔截，無法切割與排程", "groups": [], "preventive_schedule": []}
    except Exception as e:
        print(f"[index-forecast 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False,
                        "answer_text": f"指數預測與預防維護運算發生錯誤：{str(e)}", "steps": []}), 500

    months = [r["month"] for r in rows]
    y, m = (int(v) for v in months[-1].split("-"))
    fc_months = []
    for h in (1, 2, 3):
        idx = y * 12 + (m - 1) + h
        fc_months.append(f"{idx // 12:04d}-{idx % 12 + 1:02d}")
    for p in (forecast or {}).get("test_predictions_h1") or []:
        p["month"] = months[p["t"]] if p["t"] < len(months) else None
    return jsonify({
        "status": "success",
        "found": bool((forecast or {}).get("found") or dendro.get("found")),
        "ipi": {"source": ipi_source, "months": months, "values": [r["ipi"] for r in rows],
                "export_orders": [r["export_orders"] for r in rows], "utilization": [r["utilization"] for r in rows],
                "forecast_months": fc_months, "is_synthetic": ipi_source.startswith("synthetic")},
        "equipment": {"source": equip_source, "rows": equip, "indicators": inds, "is_synthetic": equip_source.startswith("synthetic")},
        "forecast": forecast, "hierarchy": hierarchy, "dendrogram": dendro,
        "steps": _merge_steps(*([forecast] if forecast else []), hierarchy, dendro),
    })


# ---------------------------------------------------------------------------
# page03：匯入整理
#   權限：沒有帳號系統。以環境變數提供兩組 token（皆可省略）：
#     IMPORT_ADMIN_TOKEN   可上傳＋可執行匯入（管理者）
#     IMPORT_UPLOAD_TOKEN  只能上傳（工程師）
#   兩者都沒設定時視為「本機開發模式」：任何人可上傳與匯入（預設只綁定 127.0.0.1）。
#   token 以請求標頭 X-Import-Token 傳入，用 hmac.compare_digest 比對。
# ---------------------------------------------------------------------------
_IMPORT_LOCK = threading.Lock()
IMPORT_EXT = (".pdf", ".csv", ".md")
IMPORT_MAX_BYTES = 5 * 1024 * 1024
IMPORT_MAX_FILES = 10
_TYPE_BY_DATASET = {"sensor_history": "感測器圖資", "failure_history": "維修履歷", "equipment_risk": "維修履歷"}


def _import_role():
    admin = os.environ.get("IMPORT_ADMIN_TOKEN", "")
    up = os.environ.get("IMPORT_UPLOAD_TOKEN", "")
    if not admin and not up:
        return "admin", False
    given = request.headers.get("X-Import-Token", "")
    if admin and given and hmac.compare_digest(given.encode(), admin.encode()):
        return "admin", True
    if up and given and hmac.compare_digest(given.encode(), up.encode()):
        return "uploader", True
    return None, True


def _deny(role, need):
    if role is None:
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "未授權：請提供有效的 X-Import-Token"}), 401
    if need == "admin" and role != "admin":
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "權限不足：只有管理者可以執行匯入（工程師可上傳檔案）"}), 403
    return None


@app.route("/api/import/session", methods=["GET"])
def api_import_session():
    role, required = _import_role()
    return jsonify({"status": "success", "auth_required": required, "role": role,
                    "limits": {"max_bytes": IMPORT_MAX_BYTES, "max_files": IMPORT_MAX_FILES, "extensions": list(IMPORT_EXT)}})


@app.route("/api/import/upload", methods=["POST"])
def api_import_upload():
    role, _ = _import_role()
    denied = _deny(role, "uploader")
    if denied:
        return denied
    files = request.files.getlist("files")
    if not files:
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "沒有收到檔案（欄位名稱需為 files）"}), 400
    if len(files) > IMPORT_MAX_FILES:
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": f"一次最多上傳 {IMPORT_MAX_FILES} 個檔案"}), 400
    updir = os.path.join(BASE_DIR, "data", "uploads")
    os.makedirs(updir, exist_ok=True)
    saved, rejected = [], []
    for fs in files:
        orig = os.path.basename((fs.filename or "").replace("\\", "/")) or "unnamed"
        ext = os.path.splitext(orig)[1].lower()
        if ext not in IMPORT_EXT:
            rejected.append({"name": orig[:80], "reason": f"不支援的副檔名 {ext or '(無)'}（只支援 .pdf、.csv、.md）"})
            continue
        data = fs.stream.read(IMPORT_MAX_BYTES + 1)
        if len(data) > IMPORT_MAX_BYTES:
            rejected.append({"name": orig[:80], "reason": f"超過單檔上限 {IMPORT_MAX_BYTES // 1048576}MB"})
            continue
        if not data:
            rejected.append({"name": orig[:80], "reason": "檔案是空的"})
            continue
        if ext == ".pdf" and not data.startswith(b"%PDF-"):
            rejected.append({"name": orig[:80], "reason": "副檔名是 PDF 但內容不是有效的 PDF"})
            continue
        if ext in (".csv", ".md") and b"\x00" in data[:4096]:
            rejected.append({"name": orig[:80], "reason": "含有二進位內容，不是文字檔"})
            continue
        base = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", os.path.splitext(orig)[0])[:60] or "file"
        stored = f"{secrets.token_hex(6)}_{base}{ext}"
        with open(os.path.join(updir, stored), "wb") as fh:
            fh.write(data)
        info = {"id": stored, "original_name": orig[:120], "size": len(data), "ext": ext[1:], "columns": None,
                "dataset": None, "dataset_label": None, "suggested_type": "設備規格書"}
        if ext == ".csv":
            info["suggested_type"] = "製程數據"
            try:
                headers, _rows = read_csv_file(data)
                info["columns"] = headers[:30]
                ds = detect_dataset(headers)
                if ds:
                    info["dataset"] = ds
                    info["suggested_type"] = _TYPE_BY_DATASET.get(ds, "製程數據")
            except Exception:       # noqa: BLE001  欄位預覽失敗不影響上傳；匯入時會再檢查並回報原因
                pass
        saved.append(info)
    return jsonify({"status": "success", "found": bool(saved), "files": saved, "rejected": rejected, "role": role})


@app.route("/api/import", methods=["POST"])
def api_import():
    role, _ = _import_role()
    denied = _deny(role, "admin")
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    files = data.get("files")
    rules = data.get("rules")
    publish = data.get("publish", True)
    if not isinstance(files, list) or not files or any(not isinstance(f, dict) for f in files):
        return jsonify({"status": "error", "found": False, "steps": [],
                        "answer_text": "files 必須是非空的物件陣列（每項含 id、file_type）"}), 400
    if not isinstance(publish, bool):
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "publish 必須是 true 或 false"}), 400
    entries = [{"name": f.get("id"), "file_type": f.get("file_type"), "original_name": f.get("original_name")} for f in files]
    if not _IMPORT_LOCK.acquire(blocking=False):
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "另一個匯入正在進行中，請稍後再試"}), 409
    try:
        r27 = import_kb_files(files=entries, rules=rules)
        publishes, refresh_results = [], []
        staged_all = [f.get("staged_csv") for f in r27.get("files", []) if f.get("staged_csv")]
        if r27.get("found") and publish:
            for f in r27["files"]:
                if not (f.get("staged_csv") and f.get("dataset")):
                    continue
                spath = os.path.abspath(os.path.join(BASE_DIR, f["staged_csv"]))
                if not spath.startswith(os.path.join(BASE_DIR, "data", "staging") + os.sep) or not os.path.isfile(spath):
                    continue
                pub = publish_dataset(spath, f["dataset"])
                pub["file"] = f["file_name"]
                try:                                        # 記錄發佈結果，page04 顯示各資料集最近一次發佈
                    kb_log_publish(pub, datetime.now().isoformat(timespec="seconds"))
                except Exception:                           # noqa: BLE001  記錄失敗不應影響匯入本身
                    print(f"[publish 記錄失敗]\n{traceback.format_exc()}", file=sys.stderr)
                pub["refreshed"] = []
                if pub.get("ok"):
                    for rr in refresh_dataset(f["dataset"]):
                        refresh_results.append(rr)
                        pub["refreshed"].append({k: rr.get(k) for k in ("skill", "ok", "found", "guardrail_status", "answer_text")})
                publishes.append(pub)
        for rel in staged_all:                              # 清掉沒被發佈（仍留在暫存）的檔案
            try:
                p = os.path.abspath(os.path.join(BASE_DIR, rel))
                if p.startswith(os.path.join(BASE_DIR, "data", "staging") + os.sep) and os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass
    except Exception as e:
        print(f"[import 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"匯入發生錯誤：{str(e)}", "steps": []}), 500
    finally:
        _IMPORT_LOCK.release()

    n = len(r27.get("files", []))
    fl = r27.get("files", [])

    def card(key, title, fail_stages, reached_pred, detail):
        failed = [f for f in fl if f.get("failure_stage") in fail_stages]
        reached = [f for f in fl if reached_pred(f)]
        if failed and not reached:
            status = "failed"
        elif failed:
            status = "warn"
        elif reached:
            status = "ok"
        else:
            status = "skipped"
        return {"key": key, "title": title, "status": status, "detail": detail}

    ok_stage = lambda st: (lambda f: f["stages"].get(st) == "ok")      # noqa: E731
    progress = [
        card("read", "讀取", ("read",), ok_stage("read"), f"{sum(1 for f in fl if f['stages'].get('read') == 'ok')}/{n} 個檔案讀取成功，共 {r27.get('rows_read', 0)} 筆"),
        card("clean", "清理", ("clean",), ok_stage("clean"), f"保留 {r27.get('rows_cleaned_count', 0)} 筆（含去重後）"),
        card("dedupe", "去重", ("dedupe",), ok_stage("dedupe"), f"重複率 {r27.get('duplicate_rate_pct', 0)}%，移除 {r27.get('duplicates_removed', 0)} 筆"),
        card("chunk", "核對、切片與寫入", ("reconcile", "chunk"), ok_stage("reconcile"), f"產生 {r27.get('chunks_created_count', 0)} 個切片並寫入文件索引"),
    ]
    pub_ok = [p for p in publishes if p.get("ok")]
    pub_bad = [p for p in publishes if not p.get("ok")]
    if not publish:
        rc = {"status": "skipped", "detail": "未勾選「發佈為分析資料集並重算」"}
    elif not publishes:
        rc = {"status": "skipped", "detail": "沒有可發佈的結構化資料集（欄位未對上已知資料集，或檔案已匯入過）"}
    elif pub_bad:
        rc = {"status": "failed" if not pub_ok else "warn", "detail": "；".join(f"{p['file']}：{p['error']}" for p in pub_bad)}
    else:
        rc = {"status": "ok", "detail": f"發佈 {len(pub_ok)} 個資料集並重跑 {len(refresh_results)} 個 Skill，結果已存成 JSON"}
    progress.append({"key": "recompute", "title": "重算模型結果檔", **rc})
    for rr in refresh_results:
        rr.pop("raw", None)
    return jsonify({
        "status": "success", "found": bool(r27.get("found")), "role": role,
        "import": {k: v for k, v in r27.items() if k != "steps"},
        "progress": progress, "publishes": publishes, "totals": kb_totals(),
        "steps": _merge_steps(r27, *refresh_results),
    })


@app.route("/api/import/logs", methods=["GET"])
def api_import_logs():
    role, _ = _import_role()
    denied = _deny(role, "uploader")
    if denied:
        return denied
    try:
        limit = int(request.args.get("limit", 30))
    except ValueError:
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "limit 必須是整數"}), 400
    return jsonify({"status": "success", "logs": kb_recent_logs(limit), "totals": kb_totals()})


# ---------------------------------------------------------------------------
# page04：維運與回答品質評估
#   權限（沿用 X-Import-Token 標頭）：
#     IMPORT_ADMIN_TOKEN   管理者：可按「立即檢查」「執行命中率測試」（會重算並覆蓋結果檔）
#     OPS_VIEW_TOKEN       廠長（唯讀）：只能讀取最近一次的結果，不能重算
#   三個 token 都沒設定時視為本機開發模式（任何人都是管理者）。工程師的上傳 token 不能使用本頁。
#   網頁預設只讀結果檔；按鈕才會重新計算（規格：網頁只讀結果，不在使用者按下時隨意重算）。
# ---------------------------------------------------------------------------
SYSTEM_VERSION = "v2.0（規格 v2 統一版）"
_EVAL_LOCK = threading.Lock()


def _ops_role():
    admin = os.environ.get("IMPORT_ADMIN_TOKEN", "")
    up = os.environ.get("IMPORT_UPLOAD_TOKEN", "")
    view = os.environ.get("OPS_VIEW_TOKEN", "")
    if not (admin or up or view):
        return "admin", False
    given = request.headers.get("X-Import-Token", "")
    if admin and given and hmac.compare_digest(given.encode(), admin.encode()):
        return "admin", True
    if view and given and hmac.compare_digest(given.encode(), view.encode()):
        return "viewer", True
    return None, True


def _ops_deny(role, need):
    if role is None:
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "未授權：請提供有效的 X-Import-Token"}), 401
    if need == "admin" and role != "admin":
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "權限不足：只有管理者可以重新檢查或重跑評估（廠長為唯讀）"}), 403
    return None


def _read_saved(name):
    path = os.path.join(BASE_DIR, "data", name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _ops_body():
    data = request.get_json(silent=True)
    if data is None and request.data:
        return None, (jsonify({"status": "error", "found": False, "steps": [], "answer_text": "請求內容不是有效的 JSON"}), 400)
    if data is not None and not isinstance(data, dict):
        return None, (jsonify({"status": "error", "found": False, "steps": [], "answer_text": "請求內容必須是 JSON 物件"}), 400)
    return data or {}, None


@app.route("/api/ops/session", methods=["GET"])
def api_ops_session():
    role, required = _ops_role()
    return jsonify({"status": "success", "auth_required": required, "role": role, "system_version": SYSTEM_VERSION})


@app.route("/api/ops/last", methods=["GET"])
def api_ops_last():
    role, _ = _ops_role()
    denied = _ops_deny(role, "viewer")
    if denied:
        return denied
    return jsonify({"status": "success", "role": role, "system_version": SYSTEM_VERSION,
                    "freshness": _read_saved("data_freshness_result.json"),
                    "eval": _read_saved("retrieval_quality_result.json")})


@app.route("/api/ops/freshness", methods=["POST"])
def api_ops_freshness():
    role, _ = _ops_role()
    denied = _ops_deny(role, "admin")
    if denied:
        return denied
    body, err = _ops_body()
    if err:
        return err
    try:
        r = check_data_freshness(today=body.get("today"), max_lag_months=body.get("max_lag_months", 3),
                                 decay_lambda=body.get("decay_lambda", 0.1), system_version=SYSTEM_VERSION)
    except Exception as e:
        print(f"[freshness 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"新鮮度檢查發生錯誤：{str(e)}", "steps": []}), 500
    return jsonify({"status": r.get("status", "success"), "found": r.get("found", False), "freshness": r,
                    "system_version": SYSTEM_VERSION, "steps": r.get("steps", [])})


@app.route("/api/ops/eval", methods=["POST"])
def api_ops_eval():
    role, _ = _ops_role()
    denied = _ops_deny(role, "admin")
    if denied:
        return denied
    body, err = _ops_body()
    if err:
        return err
    if not _EVAL_LOCK.acquire(blocking=False):
        return jsonify({"status": "error", "found": False, "steps": [], "answer_text": "另一個命中率測試正在進行中，請稍後再試"}), 409
    try:
        # 題庫路徑不由前端指定：一律使用 data/eval/gold_20.json（不存在時才自動產生）
        r = evaluate_retrieval_quality(top_k=body.get("top_k", 3), threshold=body.get("threshold", 0.10))
    except Exception as e:
        print(f"[eval 失敗]\n{traceback.format_exc()}", file=sys.stderr)
        return jsonify({"status": "error", "found": False, "answer_text": f"命中率測試發生錯誤：{str(e)}", "steps": []}), 500
    finally:
        _EVAL_LOCK.release()
    return jsonify({"status": r.get("status", "success"), "found": r.get("found", False), "eval": r,
                    "system_version": SYSTEM_VERSION, "steps": r.get("steps", [])})


if __name__ == "__main__":
    # 預設只綁定本機；要開放區網請設定 HOST=0.0.0.0（且務必關閉 FLASK_DEBUG）
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print("==================================================")
    print("🚀 製造知識庫智慧工作台 (Flask 後端伺服器) 已啟動")
    print(f"🌐 請在瀏覽器中開啟: http://{host}:{port}")
    if not ANYTHINGLLM_API_KEY:
        print("⚠️  尚未設定 ANYTHINGLLM_API_KEY，/api/search 將無法連線 AnythingLLM")
    print("==================================================")
    app.run(host=host, port=port, debug=debug)
