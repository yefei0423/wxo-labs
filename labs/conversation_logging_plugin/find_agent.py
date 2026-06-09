# ---
# **Author:** Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# *No bug too small, no syntax too weird.*
# ---
import os
from dotenv import load_dotenv
from ibm_watsonx_orchestrate import Orchestrate

load_dotenv("../.env")

API_KEY = os.getenv("WO_NEW_API_KEY")
URL = os.getenv("WO_NEW_INSTANCE_URL")

print(f"🔍 Searching for 'conversation_logger_agent' on {URL}...")

orchestrate = Orchestrate(api_key=API_KEY, url=URL)
agents = orchestrate.agents.list()

for agent in agents:
    if agent.name == "conversation_logger_agent":
        print(f"✅ FOUND: {agent.name} [ID: {agent.id}]")
        break
else:
    print("❌ Agent not found in the list.")
