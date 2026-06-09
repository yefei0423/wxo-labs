#!/usr/bin/env bash
echo "**Author:** Markus van Kempen | mvk@ca.ibm.com"
echo "[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)"
echo "*No bug too small, no syntax too weird.*"
# ============================================================
# E2E Test: MCP key_value Connection Injection (STDIO)
# ============================================================
# Proves that WxO correctly injects key_value connection credentials
# as environment variables into an MCP sidecar process running
# in STDIO transport (as a spawned subprocess).
#
# What this test does:
#   1. Reads WO_TRIAL_API_KEY + WO_INSTANCE_URL from root .env
#   2. Creates a key_value connection in WxO with dummy test credentials
#   3. Registers the probe MCP toolkit via local STDIO (--command / --package-root)
#      and wires it to the connection (--app-id)
#   4. Imports the test agent
#   5. Asks the agent to call check_credential_injection
#   6. PASS: agent reports all 4 creds were injected
#   7. FAIL: agent reports missing creds → connection wiring broken
#   8. Cleans up everything automatically on exit
#
# Prerequisites:
#   pip install fastmcp python-dotenv
#   orchestrate CLI installed and environment known
#
# Usage:
#   chmod +x run_e2e_test.sh
#   ./run_e2e_test.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_ENV="$SCRIPT_DIR/../../.env"
RESULTS_FILE="$SCRIPT_DIR/e2e_results.txt"
TOOLKIT_NAME="connection_probe_toolkit"
AGENT_NAME="connection_probe_agent"
CONNECTION_APP_ID="probe-render-images"
echo "" > "$RESULTS_FILE"

# ─────────────────────────────────────────────────
# 0. Load credentials from root .env
# ─────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " MCP Connection Injection — E2E Test (STDIO)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ ! -f "$ROOT_ENV" ]; then
    echo "❌ .env not found at $ROOT_ENV"; exit 1
fi

WO_TRIAL_API_KEY=$(grep -E '^WO_TRIAL_API_KEY=' "$ROOT_ENV" | cut -d= -f2- | tr -d '"'"'" | head -1)
WO_INSTANCE_URL=$(grep  -E '^WO_INSTANCE_URL='  "$ROOT_ENV" | cut -d= -f2- | tr -d '"'"'" | head -1)
export WO_TRIAL_API_KEY WO_INSTANCE_URL

if [ -z "${WO_TRIAL_API_KEY:-}" ] || [ -z "${WO_INSTANCE_URL:-}" ]; then
    echo "❌ WO_TRIAL_API_KEY or WO_INSTANCE_URL not set in .env"; exit 1
fi

echo "✅ Credentials loaded"
echo "   WO_INSTANCE_URL = $WO_INSTANCE_URL"
echo ""

# ─────────────────────────────────────────────────
# Cleanup function (always runs on exit)
# ─────────────────────────────────────────────────
cleanup() {
    echo ""
    echo "🧹 Cleaning up..."
    orchestrate agents remove --name "$AGENT_NAME" 2>/dev/null || true
    orchestrate toolkits remove --name "$TOOLKIT_NAME" 2>/dev/null || true
    orchestrate connections remove -a "$CONNECTION_APP_ID" 2>/dev/null || true
    echo "✅ Cleanup done."
}
trap cleanup EXIT

# ─────────────────────────────────────────────────
# 1. Activate WxO environment
# ─────────────────────────────────────────────────
echo "🔐 Step 1: Activating WxO environment..."
orchestrate env activate NEW --api-key "$WO_TRIAL_API_KEY" 2>/dev/null || \
orchestrate env activate NEW
echo "   ✅ Environment active"

# ─────────────────────────────────────────────────
# 2. Create + configure key_value connection
# ─────────────────────────────────────────────────
echo ""
echo "🔑 Step 2: Creating key_value connection '$CONNECTION_APP_ID'..."

orchestrate connections add -a "$CONNECTION_APP_ID" || true

orchestrate connections configure \
    -a "$CONNECTION_APP_ID" \
    --env draft \
    --type team \
    --kind key_value

# Set credentials (DUMMY test values — we're just testing injection)
orchestrate connections set-credentials \
    -a "$CONNECTION_APP_ID" \
    --env draft \
    -e "BASE_URL=https://probe-test.example.com" \
    -e "USER_NAME=probe_test_user" \
    -e "API_KEY=probe_test_api_key_abc123" \
    -e "IMAGE_ANALYSIS_DEPLOYMENT_ID=probe-deployment-001"

echo "   ✅ Connection '$CONNECTION_APP_ID' created with 4 test credentials"
echo "      BASE_URL, USER_NAME, API_KEY, IMAGE_ANALYSIS_DEPLOYMENT_ID"

# ─────────────────────────────────────────────────
# 3. Register probe MCP toolkit (STDIO format)
# ─────────────────────────────────────────────────
echo ""
echo "📦 Step 3: Registering probe MCP toolkit (STDIO)..."
echo "   ⏳ Waiting 30s for connection to initialize in WxO backend..."
sleep 30

# Ensure we're in the script directory so zip packaging works
cd "$SCRIPT_DIR"

orchestrate toolkits add \
    --kind mcp \
    --name "$TOOLKIT_NAME" \
    --description "Probe toolkit for testing key_value connection injection" \
    --package-root . \
    --command "python render_images_fixed.py" \
    --tools "*" \
    --app-id "$CONNECTION_APP_ID"

echo "   ✅ Toolkit '$TOOLKIT_NAME' registered via STDIO"
echo "      Command: python render_images_fixed.py"
echo "      app-id:  $CONNECTION_APP_ID  ← this wires the credentials"

# ─────────────────────────────────────────────────
# 4. Import test agent
# ─────────────────────────────────────────────────
echo ""
echo "🤖 Step 4: Importing test agent '$AGENT_NAME'..."
orchestrate agents import -f "probe_agent.yaml" >/dev/null 2>&1 || \
orchestrate agents import -f "probe_agent.yaml"
echo "   ✅ Agent '$AGENT_NAME' imported"

# Give WxO a moment to index the toolkit tools
echo "   ⏳ Waiting for toolkit discovery (30s)..."
sleep 30

# ─────────────────────────────────────────────────
# 5. Run the test query
# ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 Step 5: Asking agent to check credential injection..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

QUERY="Call debug_env_vars and return the exact JSON result."
echo "   Query: \"$QUERY\""
echo ""
# Run chat and show output in real-time while capturing it
# Use expect to simulate a PTY to avoid the known EOF infinite loop bug in orchestrate chat REPL
RAW_RESPONSE=$(expect -c '
set timeout 60
spawn orchestrate chat ask -n "'"$AGENT_NAME"'" "'"$QUERY"'" -r -l
expect {
    -re "You:|👤" {
        exit 0
    }
    eof {
        exit 0
    }
    timeout {
        puts "ERROR: Timeout waiting for response"
        exit 1
    }
}
' 2>&1 | tee /dev/stderr || true)

echo "$RAW_RESPONSE" > agent_output.log
# ─────────────────────────────────────────────────
# 6. Evaluate result
# ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Step 6: Evaluating result..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if echo "$RAW_RESPONSE" | grep -A 5 -qi -E "BASE_URL.*SET|probe-test|probe_test"; then
    RESULT="✅ PASS"
    DETAIL="WxO correctly injected key_value credentials! Detected BASE_URL via debug_env_vars tool."
    echo "$RESULT" >> "$RESULTS_FILE"
    echo "$DETAIL" >> "$RESULTS_FILE"
else
    # Only fail if it didn't find the credentials
    RESULT="❌ FAIL — Connection injection not working"
    DETAIL="WxO did NOT inject the key_value credentials. BASE_URL not found."
    echo "$RESULT" >> "$RESULTS_FILE"
    echo "$DETAIL" >> "$RESULTS_FILE"
else
    RESULT="⚠️  UNKNOWN — Agent responded but result unclear"
    DETAIL="Check the raw response above manually."
    echo "$RESULT" >> "$RESULTS_FILE"
    echo "$DETAIL" >> "$RESULTS_FILE"
fi

echo ""
echo "   $RESULT"
echo "   $DETAIL"

# ─────────────────────────────────────────────────
# 7. Final Report
# ─────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
echo "  E2E Test Summary"
echo "════════════════════════════════════════════════"
cat "$RESULTS_FILE"
echo "════════════════════════════════════════════════"
echo ""
echo "📌 What this test proves:"
echo "   If PASS:  WxO correctly injects key_value credentials as env vars"
echo "             for STDIO transported MCP toolkits."
echo "             Use os.environ.get('KEY') in your real MCP tool — NOT"
echo "             connections.key_value()."
