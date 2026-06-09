#!/usr/bin/env bash
# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com
# ---
# Deploy the askHR context variables E2E test to WatsonX Orchestrate.
#
# What this script does:
#   1. Validates prerequisites (CLI, .env, active environment, ngrok URL)
#   2. Imports the OpenAPI tool (Pattern A — LLM-mediated context injection)
#   3. Imports the Python tool (Pattern C — direct request_context read)
#   4. Imports and deploys the askHR_agent
#
# Usage:
#   ./deploy_to_wxo.sh
#
# Prerequisites:
#   - .env file with WO_INSTANCE_URL, WO_TRIAL_API_KEY
#   - An active WxO environment: orchestrate env activate <ENV_NAME>
#   - ngrok running: ngrok http 8000
#   - mcp_hr_context_server.py running: python mcp_hr_context_server.py
#   - hr_context_openapi.json updated with your ngrok URL
# ---

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠️  $*${RESET}"; }
err()  { echo -e "${RED}❌ $*${RESET}"; exit 1; }
info() { echo -e "${CYAN}   $*${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
OPENAPI_SPEC="${SCRIPT_DIR}/hr_context_openapi.json"
PYTHON_TOOL="${SCRIPT_DIR}/tools/hr_context_python_tool.py"
AGENT_YAML="${SCRIPT_DIR}/agents/askhr_agent.yaml"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  askHR Context Variables E2E Test — Deploy to WxO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Step 1: Prerequisites ──────────────────────────────────────────────────────
echo "Step 1 — Checking prerequisites"

if ! command -v orchestrate &>/dev/null; then
    err "orchestrate CLI not found. Install the IBM WxO ADK first."
fi
ok "orchestrate CLI found"

if [ ! -f "$ENV_FILE" ]; then
    warn ".env not found. Copy .env.template → .env and fill in your credentials."
    warn "Continuing without sourcing .env..."
else
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    ok ".env loaded"
fi

# Verify an active environment is set
ACTIVE_ENV=$(orchestrate env list 2>/dev/null | grep "(active)" | awk '{print $1}' || true)
if [ -z "$ACTIVE_ENV" ]; then
    err "No active WxO environment. Run: orchestrate env activate <ENV_NAME>"
fi
ok "Active WxO environment: ${ACTIVE_ENV}"

# Warn if ngrok URL is still the placeholder
if grep -q "REPLACE_WITH_YOUR_NGROK_URL" "$OPENAPI_SPEC"; then
    warn "hr_context_openapi.json still has placeholder URL."
    warn "Run 'ngrok http 8000', copy the https URL, and update 'servers[0].url' in hr_context_openapi.json"
    warn "Continuing — you must update the URL before the OpenAPI tool will work."
fi

echo ""

# ── Step 2: Import OpenAPI tool ────────────────────────────────────────────────
echo "Step 2 — Importing OpenAPI tool (get_hr_context)"

orchestrate tools import \
    --file "$OPENAPI_SPEC" \
    --kind openapi
ok "OpenAPI tool 'get_hr_context' imported"

echo ""

# ── Step 3: Import Python tool ─────────────────────────────────────────────────
echo "Step 3 — Importing Python tool (read_hr_context)"

orchestrate tools import \
    --file "$PYTHON_TOOL" \
    --kind python
ok "Python tool 'read_hr_context' imported"

echo ""

# ── Step 4: Import and deploy agent ───────────────────────────────────────────
echo "Step 4 — Importing and deploying askHR_agent"

orchestrate agents import --file "$AGENT_YAML"
ok "Agent 'askHR_agent' imported"

orchestrate agents deploy -n askHR_agent
ok "Agent 'askHR_agent' deployed"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  Deployment complete!${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Next steps:"
echo "   1. Set context variable VALUES in the WxO UI:"
echo "      https://dl.watson-orchestrate.ibm.com → Settings → Context Variables"
echo "      Add each variable with its value:"
echo "        clientID  = CLIENT-001"
echo "        name      = Jane Doe"
echo "        role      = HR Manager"
echo "        user_name = jdoe"
echo "        email_id  = jdoe@example.com"
echo ""
echo "      NOTE: 'orchestrate context' does not exist as a CLI command."
echo "      Context variable values must be set via the WxO UI or REST API."
echo ""
echo "   2. Run the E2E test:"
echo "      ./run_e2e_test.sh"
echo ""
echo "   3. Or chat directly:"
echo "      echo 'q' | orchestrate chat ask -n askHR_agent 'show my HR context'"
echo ""
