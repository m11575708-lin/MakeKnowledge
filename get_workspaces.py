import requests

url = "http://127.0.0.1:3001/api/v1/workspaces"
headers = {
    "Authorization": "Bearer 9RWGJ55-ZSVMBEQ-P210H1F-P5M3GKN",
    "Content-Type": "application/json",
}

try:
    response = requests.get(url, headers=headers)
    print(f"狀態碼: {response.status_code}")
    print(f"回傳工作區清單: {response.text}")
except Exception as e:
    print(f"發生錯誤: {e}")