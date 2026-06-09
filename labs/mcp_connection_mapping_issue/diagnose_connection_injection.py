#!/usr/bin/env python3
"""
diagnose_connection_injection.py
=================================
Quick diagnostic script to verify that WxO is correctly injecting
credentials from the key_value connection as environment variables.

Run this BEFORE the full MCP server to confirm the env vars are present:

  LOCAL (from your .env):
    python diagnose_connection_injection.py

  IN WXO (via orchestrate chat or MCP logs):
    The MCP server stdout/stderr shows these diagnostics on startup.

Usage:
    python diagnose_connection_injection.py

Author: Markus van Kempen | mvk@ca.ibm.com
"""

import os
import sys
from dotenv import load_dotenv

# Load .env for local testing; WxO env vars override these when deployed
load_dotenv()

REQUIRED_KEYS = [
    "BASE_URL",
    "USER_NAME",
    "API_KEY",
    "IMAGE_ANALYSIS_DEPLOYMENT_ID",
]


def diagnose():
    print("=" * 55)
    print("  WxO MCP Connection Injection Diagnostic")
    print("=" * 55)
    print()

    all_ok = True
    for key in REQUIRED_KEYS:
        val = os.environ.get(key)
        if val:
            # Show first 20 chars only for security
            display = val[:20] + "..." if len(val) > 20 else val
            print(f"  ✅ {key:<40} = {display}")
        else:
            print(f"  ❌ {key:<40} = NOT FOUND")
            all_ok = False

    print()

    if all_ok:
        print("✅ All credentials found.")
        print()
        print("   If running locally: credentials came from your .env file.")
        print("   If running in WxO:  credentials were injected by the")
        print("   platform from your key_value connection 'render_images'.")
    else:
        print("❌ Missing credentials detected.\n")
        print("   If running LOCALLY:")
        print("     1. Copy .env.example to .env")
        print("     2. Fill in the real values")
        print("     3. Re-run this script\n")
        print("   If running IN WxO (and you see this in the logs):")
        print("     1. Verify you ran:")
        print("          orchestrate connections set-credentials -a render_images --env draft \\")
        print("            -e BASE_URL=xxx -e USER_NAME=xxx \\")
        print("            -e API_KEY=xxx -e IMAGE_ANALYSIS_DEPLOYMENT_ID=xxx")
        print("     2. Verify the toolkit was registered with --app-id 'render_images':")
        print("          orchestrate toolkits add --kind mcp --name ... --app-id render_images ...")
        print("     3. The key names in -e must EXACTLY match what the code reads via os.environ.get()")
        sys.exit(1)

    print()
    print("=" * 55)


if __name__ == "__main__":
    diagnose()
