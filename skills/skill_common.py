# -*- coding: utf-8 -*-
"""
skill_common.py — 所有 Skill 共用的小工具（純 Python 標準庫）

注意：MCP 以 STDIO 通訊，stdout 專供協定使用，本檔與所有 Skill 只准寫 stderr，絕不 print 到 stdout。
"""
import json
import os
import sys


def project_root() -> str:
    """專案根目錄：本檔位於 skills/ 時回傳其上一層，否則回傳本檔所在目錄。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here) if os.path.basename(here).lower() == "skills" else here


def make_step(number, name, description, skill, algorithm, package) -> dict:
    """產生一筆「這個結果怎麼算的」步驟日誌（欄位對應前端三色標籤）。"""
    return {
        "step_number": number,
        "step_name": name,
        "description": description,
        "skill_name": skill,          # 🔵 藍色：Skill 模組
        "algorithm_used": algorithm,  # 🟣 紫色：課堂演算法
        "package_used": package,      # ⚫ 灰色：使用套件
    }


def save_json(result: dict, filename: str, output_json_path=None) -> str:
    """把結果寫成 JSON 檔（預設 <專案根>/output/<filename>），失敗只記錄 stderr，不中斷主流程。"""
    path = output_json_path or os.path.join(project_root(), "output", filename)
    result["output_json_path"] = path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return path
    except (OSError, TypeError, ValueError) as e:
        print(f"[save_json 失敗] {path}: {e}", file=sys.stderr)
        result["output_json_path"] = ""
        return ""
