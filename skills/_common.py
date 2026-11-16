"""
_common.py - 所有 Skill 共用的小工具

- StepLog：統一產生「5 步透明化推導日誌」(steps 陣列)，欄位與 skill_01 完全一致
- save_json / default_output_path：結果寫出到專案根目錄的 data/ 資料夾
"""

import json
import os


def project_root() -> str:
    """skills/ 的上一層即專案根目錄。"""
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def default_output_path(filename: str) -> str:
    return os.path.join(project_root(), "data", filename)


def save_json(result: dict, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


class StepLog:
    """
    以 plan（固定 5 個 (步驟名稱, 演算法, 套件) 三元組）建立 steps。
    每次 add() 依序填入下一步；若中途被 Guardrail 攔截，
    skip_to_last() 會把中間步驟標記為「已略過」，確保輸出仍是完整 5 步。
    """

    def __init__(self, skill_name: str, plan: list):
        self.skill_name = skill_name
        self.plan = plan
        self.steps = []

    def add(self, description: str) -> None:
        n = len(self.steps) + 1
        if n > len(self.plan):
            raise RuntimeError("steps 超過 plan 定義的步驟數")
        name, algorithm, package = self.plan[n - 1]
        self.steps.append({
            "step_number": n,
            "step_name": name,
            "description": description,
            "skill_name": self.skill_name,
            "algorithm_used": algorithm,
            "package_used": package,
        })

    def skip_to_last(self, reason: str) -> None:
        while len(self.steps) < len(self.plan) - 1:
            self.add(f"已略過：{reason}")
