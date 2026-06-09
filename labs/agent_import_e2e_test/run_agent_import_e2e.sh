#!/bin/bash
echo "**Author:** Markus van Kempen | mvk@ca.ibm.com"
echo "[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)"
echo "*No bug too small, no syntax too weird.*"
# ---
# Agent Import E2E Test
# ---
set -e

echo "🚀 Starting Agent Import E2E Test..."

echo "📦 Importing Toolkit..."
orchestrate toolkits add --name long_running_toolkitv3 --kind python --description "Toolkit for long-running operations" --package-root input_blocking_test_agentv3/tools/long_running_toolv3

echo "🔌 Importing Plugin..."
orchestrate toolkits add --name blocking_pluginv3 --kind python --description "Pre-invoke plugin for input blocking" --package-root input_blocking_test_agentv3/plugins/blocking_pluginv3

echo "🤖 Importing Agent..."
# Note: The agent.agent.yaml already has the correct names.
# The ADK will link them automatically if they are registered.
orchestrate agents import -f input_blocking_test_agentv3/agents/agent.agent.yaml

echo "🔍 Verifying Agent Status..."
orchestrate agents list --verbose | grep -q "input_blocking_test_agentv3"

echo "✅ Success! Agent and dependencies imported successfully."
