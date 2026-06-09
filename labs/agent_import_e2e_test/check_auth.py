# ---
# **Author:** Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# *No bug too small, no syntax too weird.*
# ---
import requests
import os
from dotenv import load_dotenv

load_dotenv()

base_url = "https://api.dl.watson-orchestrate.ibm.com/instances/20260409-1024-1886-70e4-25304afe4a1b"
api_key = "azE6dXNyXzQ5Y2M4MWExLWEyYjAtM2MxYy04N2ViLWJmMjQ1YzdkNzE4NDpKUEZyWlppQWl5VEp4NzV0V3FjSmxUd29LaG1COUY0ejgwa21NbHRrc3lzPTp4R2dE"

def check_auth():
    print(f"🔍 Checking auth for {base_url}...")
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }
    # Try to list toolkits
    url = f"{base_url}/toolkits"
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

if __name__ == "__main__":
    check_auth()
