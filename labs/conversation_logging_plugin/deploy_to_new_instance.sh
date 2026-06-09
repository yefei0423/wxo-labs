#!/usr/bin/env bash
# Deploy Logging Plugin and Agent to the WO_NEW Instance
# ============================================================
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# *No bug too small, no syntax too weird.*
# ============================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Load credentials from .env
if [ -f "$SCRIPT_DIR/../.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/../.env" | xargs)
fi

# Ensure we use the NEW instance for the CLI
export ORCHESTRATE_API_KEY="$WO_NEW_API_KEY"
export ORCHESTRATE_URL="$WO_NEW_INSTANCE_URL"

echo "🚀 Deploying to: $ORCHESTRATE_URL"

# 2. Import Tool/Plugin
echo "📥 Importing logging_plugin..."
orchestrate tools import --kind python -f "$SCRIPT_DIR/logging_plugin.py" --name "logging_plugin"

# 3. Import Agent
echo "📥 Importing conversation_logger_agent..."
# Using the agent.yaml we created earlier
orchestrate agents import -f "$SCRIPT_DIR/agent.yaml"

echo "✅ Deployment complete. Fetching Agent ID..."
orchestrate agents list | grep conversation_logger_agent || echo "Agent imported but not listed yet."
