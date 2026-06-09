#!/usr/bin/env python3
# ==============================================================================
# Diagnostic: Find WxO SAML/SSO Endpoints
# ==============================================================================
# **Author:** Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ==============================================================================

import os
import sys

def find_endpoints():
    env_path = "../../.env"
    if not os.path.exists(env_path):
        print("❌ Error: .env file not found in parent directory.")
        return

    instance_url = None
    with open(env_path, "r") as f:
        for line in f:
            if "WO_NEW_INSTANCE_URL=" in line:
                instance_url = line.split("=")[1].strip().strip("\"").strip("'")

    if not instance_url:
        print("❌ Error: WO_NEW_INSTANCE_URL not found in .env.")
        return

    print(f"\n📢 Watsonx Orchestrate SAML Endpoints for:")
    print(f"🔗 Base Instance: {instance_url}\n")
    
    print(f"🔹 Identifier (Entity ID):")
    print(f"   {instance_url}/saml/metadata\n")
    
    print(f"🔹 Reply URL (ACS URL):")
    print(f"   {instance_url}/saml/acs\n")
    
    print(f"🔹 Sign-on URL:")
    print(f"   {instance_url}/\n")

if __name__ == "__main__":
    find_endpoints()
