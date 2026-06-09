#!/usr/bin/env bash
# ==============================================================================
# E2E Test: SSO with WatsonX Orchestrate Connections
# ==============================================================================
# **Author:** Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ==============================================================================
# This script tests SSO identity propagation through existing WxO connections
# like Box, Salesforce, ServiceNow, etc.
# ==============================================================================

set -euo pipefail
ORC="/Users/markusvankempen/miniforge3/bin/orchestrate"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║          SSO Test with WatsonX Orchestrate Connections                     ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Load environment
export $(grep -E '^(WO_NEW_API_KEY|WO_NEW_INSTANCE_URL)=' "../../.env" | xargs)
"$ORC" env activate NEW --api-key "$WO_NEW_API_KEY" >/dev/null 2>&1

echo "🔍 Discovering available connections..."
echo ""

# List all connections
CONNECTIONS=$("$ORC" connections list 2>/dev/null || echo "")

if [[ -z "$CONNECTIONS" ]]; then
    echo "❌ No connections found or unable to list connections"
    exit 1
fi

echo "📋 Available Connections:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$CONNECTIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Prompt user to select a connection
echo "Which connection would you like to test SSO with?"
echo ""
read -p "Enter connection app_id (e.g., box, salesforce, servicenow): " APP_ID

if [[ -z "$APP_ID" ]]; then
    echo "❌ No connection specified"
    exit 1
fi

echo ""
echo "🔍 Checking connection: $APP_ID"

# Verify connection exists
if ! "$ORC" connections list | grep -q "$APP_ID"; then
    echo "❌ Connection '$APP_ID' not found"
    exit 1
fi

echo "✅ Connection found: $APP_ID"
echo ""

# List tools for this connection
echo "📦 Discovering tools for connection: $APP_ID"
TOOLS=$("$ORC" tools list 2>/dev/null | grep -i "$APP_ID" || echo "")

if [[ -z "$TOOLS" ]]; then
    echo "⚠️  No tools found for this connection"
    echo "   You may need to import tools first"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$TOOLS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create test agent that uses this connection
echo "🤖 Creating SSO test agent for connection: $APP_ID"

AGENT_NAME="sso_test_${APP_ID}_agent"
AGENT_FILE="sso_test_${APP_ID}_agent.yaml"

# Extract first tool name from the connection
FIRST_TOOL=$(echo "$TOOLS" | head -1 | awk '{print $1}' || echo "")

if [[ -z "$FIRST_TOOL" ]]; then
    echo "❌ Could not extract tool name"
    exit 1
fi

echo "   Using tool: $FIRST_TOOL"

# Create agent YAML
cat > "$AGENT_FILE" <<EOF
# ==============================================================================
# SSO Test Agent for Connection: $APP_ID
# ==============================================================================
spec_version: v1
kind: native
name: $AGENT_NAME
title: SSO Test Agent - $APP_ID
description: |
  Test agent to verify SSO identity propagation through $APP_ID connection.
  This agent will attempt to use tools from the $APP_ID connection to verify
  that user identity is correctly passed through.
instructions: |
  You are an SSO identity tester. When asked to test identity or "who am i",
  use the available tools from the $APP_ID connection. Report back any user
  information, authentication status, or identity details you can discover.
  
  If you encounter authentication prompts, that indicates SSO is working.
  If you get user information back, report the username and any roles/permissions.
tools:
  - $FIRST_TOOL
EOF

echo "   ✅ Agent definition created: $AGENT_FILE"
echo ""

# Import the agent
echo "📤 Importing agent..."
if "$ORC" agents import -f "$AGENT_FILE" >/dev/null 2>&1; then
    echo "   ✅ Agent imported successfully"
else
    echo "   ⚠️  Agent import had warnings (may already exist)"
fi

echo ""
echo "⏳ Waiting 10s for platform sync..."
sleep 10

# Test with chat
echo ""
echo "💬 Testing SSO with chat..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

/usr/bin/expect -c "
set timeout 60
spawn $ORC chat ask -n \"$AGENT_NAME\" \"Who am I? What can you tell me about my identity?\"
expect {
    \"login\" { 
        puts \"\n[TEST] ✅ SSO LOGIN PROMPT DETECTED!\"
        puts \"This indicates SSO is configured and working.\"
        exit 0 
    }
    \"authenticate\" { 
        puts \"\n[TEST] ✅ AUTHENTICATION PROMPT DETECTED!\"
        puts \"This indicates SSO flow is being triggered.\"
        exit 0 
    }
    \"username\" { 
        puts \"\n[TEST] ✅ USER IDENTITY DETECTED!\"
        puts \"This indicates an active SSO session.\"
        exit 0 
    }
    \"user\" { 
        puts \"\n[TEST] ✅ USER INFORMATION DETECTED!\"
        puts \"This indicates identity propagation is working.\"
        exit 0 
    }
    timeout { 
        puts \"\n[TEST] ⏱️  TIMEOUT - No clear SSO indication\"
        puts \"The connection may not be configured for SSO.\"
        exit 1 
    }
}
" || true

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "✅ SSO Test Complete for connection: $APP_ID"
echo ""
echo "📋 Summary:"
echo "   - Connection: $APP_ID"
echo "   - Tool tested: $FIRST_TOOL"
echo "   - Agent: $AGENT_NAME"
echo ""
echo "💡 Tips:"
echo "   - If you saw a login prompt, SSO is working correctly"
echo "   - If you saw user info, identity propagation is successful"
echo "   - If timeout occurred, the connection may need SSO configuration"
echo ""
echo "🔧 To configure SSO for this connection:"
echo "   orchestrate connections configure -a $APP_ID --sso True"
echo ""

# Made by Research | 7 1/2 Floor
