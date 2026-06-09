#!/usr/bin/env bash
set -e

# Change to the directory of the script so imports work correctly
cd "$(dirname "$0")"

# Author: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# No bug too small, no syntax too weird.

echo "=========================================="
echo " 🛡️ Watsonx Orchestrate RBAC Plugin Test"
echo "=========================================="

echo "[1] Sourcing environment variables..."
source ../../.env

echo "[2] Importing RBAC plugin tool with requirements..."
orchestrate tools import -k python -f RBAC_plugin.py -r requirements.txt

echo "[3] Importing RBAC agent definition..."
orchestrate agents import -f rbac_agent_def.yaml

echo "[4] Deploying the RBAC test agent..."
orchestrate agents deploy -n rbac_tester_agent

echo "=========================================="
echo " ✅ Deployment Complete!"
echo " Starting end-to-end test chat."
echo " Try typing 'hello' or another prompt!"
echo " Type 'q' or 'exit' when you want to quit."
echo "=========================================="

orchestrate chat ask -n rbac_tester_agent
