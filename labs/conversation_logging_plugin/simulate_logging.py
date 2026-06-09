"""
E2E Logging Simulator v2.0 (Thread-Aware)

Simulates complex conversation turns with multiple agents and unique threads
to verify the dashboard's filtering and stitching capabilities.

**Author:** Markus van Kempen | mvk@ca.ibm.com
"""

import requests
import json
from datetime import datetime

TARGET_URL = "http://localhost:5002/log"

# Turn sequence with Thread IDs
SIMULATION_SCENARIO = [
    # Conversation 1: Flight Booking
    {"type": "pre", "agent": "travel_agent", "thread": "FLIGHT-999", "msg": "I need a flight to Paris."},
    {"type": "post", "agent": "travel_agent", "thread": "FLIGHT-999", "msg": "I found 3 options. Would you like to see them?"},
    
    # Conversation 2: Password Reset
    {"type": "pre", "agent": "it_support", "thread": "IT-101", "msg": "Reset my password please."},
    {"type": "post", "agent": "it_support", "thread": "IT-101", "msg": "Sure. I've sent a verification code to your phone."},
    
    # Conversation 1 continues
    {"type": "pre", "agent": "travel_agent", "thread": "FLIGHT-999", "msg": "Yes, show me the cheapest one."},
    {"type": "post", "agent": "travel_agent", "thread": "FLIGHT-999", "msg": "Option 1: $420 with Air France."}
]

def run_simulation():
    print(f"🚀 Starting Threaded Simulation to {TARGET_URL}...")
    
    for turn in SIMULATION_SCENARIO:
        payload = {
            "agent_id": turn["agent"],
            "user_input": turn["msg"] if turn["type"] == "pre" else "N/A",
            "assistant_output": turn["msg"] if turn["type"] == "post" else "[PRE-INVOKE]",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "context": {"thread_id": turn["thread"], "user_id": "mvk@ca.ibm.com"}
        }
        
        try:
            res = requests.post(TARGET_URL, json=payload, timeout=5)
            print(f"✅ Logged {turn['type']} | Thread: {turn['thread']} | Status: {res.status_code}")
        except Exception as e:
            print(f"❌ Failed: {e}")

if __name__ == "__main__":
    run_simulation()
