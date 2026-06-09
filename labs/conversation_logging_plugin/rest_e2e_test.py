"""
REST-based End-to-End Chat Test

Directly interacts with the Watsonx Orchestrate Assistant API to verify
that Gateway plugins (Pre/Post-Invoke) are triggered correctly.

**Author:** Markus van Kempen | mvk@ca.ibm.com  
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
*No bug too small, no syntax too weird.*
"""

import os
import requests
import json
from dotenv import load_dotenv

# Load credentials
load_dotenv("../.env")
API_KEY = os.getenv("WO_NEW_API_KEY")
INSTANCE_URL = os.getenv("WO_NEW_INSTANCE_URL")
MCSP_TOKEN_URL = os.getenv("WO_MCSP_TOKEN_URL", "https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token")

def get_iam_token():
    print(f"🔑 Fetching MCSP Token from {MCSP_TOKEN_URL}...")
    try:
        # MCSP token exchange uses the API key in the body
        res = requests.post(MCSP_TOKEN_URL, json={
            "apikey": API_KEY
        })
        if res.status_code == 200:
            return res.json().get("token")
        else:
            print(f"❌ Token fetch failed: {res.text}")
            return None
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

def chat_test():
    token = get_iam_token()
    if not token:
        print("❌ Could not obtain MCSP token.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # WxO Assistant Chat Endpoint
    chat_url = f"{INSTANCE_URL}/assistant/api/v1/chat?version=2024-03-14"
    
    print(f"💬 Sending chat request to {chat_url}...")
    
    payload = {
        "input": {
            "text": "Hello Logger! Please verify this E2E test."
        },
        "agent": {
            "name": "conversation_logger_agent"
        }
    }

    try:
        res = requests.post(chat_url, headers=headers, json=payload)
        print(f"📡 Status Code: {res.status_code}")
        if res.status_code == 200:
            print("🤖 Agent Response:", res.json().get("output", {}).get("generic", [{}])[0].get("text"))
            print("\n✅ Chat Turn Completed. Check your log_receiver.py output!")
        else:
            print("❌ Error:", res.text)
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    chat_test()
