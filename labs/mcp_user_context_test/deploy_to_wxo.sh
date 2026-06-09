#!/bin/bash
echo "**Author:** Markus van Kempen | mvk@ca.ibm.com"
echo "[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)"
echo "*No bug too small, no syntax too weird.*"
set -e

echo "🚀 Deploying MCP SSE Context Tester to WxO Environment..."

# Verify CLI Environment
ACTIVE_ENV=$(orchestrate env list | grep "(active)" | awk '{print $1}')
echo "Current Active WxO Profile: $ACTIVE_ENV"

# 1. Import the Tool OpenAPI spec
echo "📦 Importing MCP Tool OpenAPI Specification..."
orchestrate tools import --file mcp_context_openapi.json --kind openapi

# Extract the Tool ID that was just created to link it to the agent
TOOL_INFO=$(orchestrate tools list | grep "get_session_identity" || true)

if [ -z "$TOOL_INFO" ]; then
    echo "⚠️ Failed to verify tool import via CLI (might take a moment to sync or require UI confirmation due to OAuth security parameters)."
else
    # The first column is the Tool ID
    TOOL_ID=$(echo "$TOOL_INFO" | awk '{print $1}')
    echo "✅ Found Tool ID: $TOOL_ID"
fi

# 2. Import the Agent
echo "🤖 Importing the Test Agent..."
orchestrate agents import --file mcp_agent_def.yaml

echo "--------------------------------------------------------"
echo "✅ Deployment Scripts Executed!"
echo ""
echo "🚦 NEXT STEPS MAPPING TO OAUTH TOOL:"
echo "1. Go to the WxO Web UI -> Agent Builder."
echo "2. Open the 'MCP Identity Tester' agent."
echo "3. Go to the Tools tab and make sure 'get_session_identity' is connected."
echo "4. Since it uses OAuth 2.0, clicking 'Connect' in the UI will ask for OAuth credentials."
echo "   - Token URL: https://iam.cloud.ibm.com/identity/token"
echo "   - Client ID: dummy"
echo "   - Client Secret: dummy"
echo "5. Now you can use 'orchestrate chat ask' or the Web UI to chat with the agent!"
echo "--------------------------------------------------------"
