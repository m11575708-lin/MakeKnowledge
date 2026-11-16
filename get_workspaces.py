"""列出 AnythingLLM 的工作區（確認 slug 用）。

金鑰一律從環境變數讀取，不要寫進程式：
  Windows PowerShell:  $env:ANYTHINGLLM_API_KEY="你的金鑰"
  macOS / Linux:       export ANYTHINGLLM_API_KEY="你的金鑰"
"""
import os
import sys

import requests

API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "")
BASE_URL = os.environ.get("ANYTHINGLLM_BASE_URL", "http://127.0.0.1:3001")

if not API_KEY:
    sys.exit("請先設定環境變數 ANYTHINGLLM_API_KEY")

url = f"{BASE_URL}/api/v1/workspaces"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

try:
    response = requests.get(url, headers=headers, timeout=30)
    print(f"狀態碼: {response.status_code}")
    print(f"回傳工作區清單: {response.text}")
except Exception as e:
    print(f"發生錯誤: {e}")
