#!/bin/bash
# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🧹 Cleaning up previous test artifacts..."
orchestrate agents remove --name mcp_repro_agent || true
orchestrate toolkits remove --name MCP_SUCCESS_PKG || true

echo "🛠️  Deploying MCP Toolkit (using --package-root)..."
orchestrate toolkits add \
  -k mcp \
  -n "MCP_SUCCESS_PKG" \
  --description "Succeeds because files are uploaded" \
  --package-root "$SCRIPT_DIR" \
  --command "bash run_stdio.sh"

echo "🤖 Importing Validation Agent..."
orchestrate agents import --file "$SCRIPT_DIR/mcp_repro_agent.json"

echo "--------------------------------------------------"
echo "✅ Deployment Complete!"
echo ""
echo "💬 To test the MCP server, run:"
echo "orchestrate chat ask -n mcp_repro_agent \"Is the MCP server working?\""
echo "--------------------------------------------------"
