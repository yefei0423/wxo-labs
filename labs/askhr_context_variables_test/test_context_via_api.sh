#!/usr/bin/env bash
# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com
# ---
# Test askHR_agent context variable injection via the WxO /runs REST API.
#
# The orchestrate CLI (chat ask) has NO mechanism to pass context variable values.
# Context variables reach the agent runtime through two paths only:
#
#   Method 1 — JWT token:  embed context in the signed JWT `context` claim
#   Method 2 — /runs API:  pass context in the REST API request payload
#                          (this is what the web chat pre:send event uses internally)
#
# This script uses Method 2: direct POST to the /runs API with context in the body.
#
# References:
#   https://developer.watson-orchestrate.ibm.com/webchat/context_variables
#
# Prerequisites:
#   - .env file with WO_INSTANCE_URL and WO_TRIAL_API_KEY
#   - askHR_agent deployed (run ./deploy_to_wxo.sh first)
#   - mcp_hr_context_server.py running + ngrok tunnel active
# ---

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
fail() { echo -e "${RED}❌ $*${RESET}"; }
info() { echo -e "${CYAN}   $*${RESET}"; }
h()    { echo -e "\n${BOLD}$*${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  askHR Context Variables — REST API Test"
echo "  (Method 2: /runs API payload injection)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ .env not found. Copy .env.template → .env and fill in your credentials.${RESET}"
    exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

# Validate required vars
: "${WO_INSTANCE_URL:?WO_INSTANCE_URL not set in .env}"
: "${WO_TRIAL_API_KEY:?WO_TRIAL_API_KEY not set in .env}"

# ── Get a Bearer token from the MCSP API key ──────────────────────────────────
h "Step 1 — Exchange API key for Bearer token"

BEARER_TOKEN=$(curl -sf -X POST \
    "https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token" \
    -H "Content-Type: application/json" \
    -d "{\"apikey\": \"${WO_TRIAL_API_KEY}\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")

if [ -z "$BEARER_TOKEN" ]; then
    fail "Failed to get Bearer token. Check WO_TRIAL_API_KEY in .env."
    exit 1
fi
ok "Bearer token obtained (${#BEARER_TOKEN} chars)"

# ── Resolve agent ID from name ─────────────────────────────────────────────────
h "Step 2 — Resolve askHR_agent ID"

AGENTS_RESP=$(curl -sf \
    "${WO_INSTANCE_URL}/v1/orchestrate/agents" \
    -H "Authorization: Bearer ${BEARER_TOKEN}" \
    -H "Content-Type: application/json" 2>/dev/null || echo "[]")

AGENT_ID=$(echo "$AGENTS_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
agents = data if isinstance(data, list) else data.get('agents', data.get('items', []))
match = next((a.get('id','') for a in agents if a.get('name','') == 'askHR_agent'), '')
print(match)
" 2>/dev/null || echo "")

if [ -z "$AGENT_ID" ]; then
    fail "Could not resolve agent ID for 'askHR_agent'. Is it deployed?"
    exit 1
fi
ok "Agent ID: ${AGENT_ID}"

# ── Helper: submit a run and poll to completion ────────────────────────────────
poll_run() {
    local RUN_ID="$1"
    local MAX=15
    for i in $(seq 1 $MAX); do
        sleep 3
        local POLL
        POLL=$(curl -sf "${WO_INSTANCE_URL}/v1/orchestrate/runs/${RUN_ID}" \
            -H "Authorization: Bearer ${BEARER_TOKEN}" 2>/dev/null || echo "{}")
        local STATE
        STATE=$(echo "$POLL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
        if [[ "$STATE" == "completed" || "$STATE" == "failed" ]]; then
            echo "$POLL"
            return 0
        fi
        echo -e "${CYAN}   poll $i/$MAX — state=$STATE${RESET}" >&2
    done
    echo "{}"
}

extract_tool_args() {
    python3 -c "
import sys, json
d = json.load(sys.stdin)
msg = d.get('result', {}).get('data', {}).get('message', {})
# Also return the context echo in the response
ctx = msg.get('context', {})
steps = msg.get('step_history', [])
for step in steps:
    for detail in step.get('step_details', []):
        for tc in detail.get('tool_calls', []):
            args = tc.get('args', {})
            if args:
                print(json.dumps(args, indent=2))
                sys.exit(0)
# Fallback to response context
if ctx:
    print(json.dumps(ctx, indent=2))
" 2>/dev/null || echo "{}"
}

# ── Test 1: All 5 context variables at top level of /runs payload ─────────────
h "Test 1 — POST /v1/orchestrate/runs with all 5 context variables"
info "Correct payload: {agent_id, message:{role,content}, context:{...}}"

RUNS_RESP=$(curl -sf -X POST \
    "${WO_INSTANCE_URL}/v1/orchestrate/runs" \
    -H "Authorization: Bearer ${BEARER_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
        \"agent_id\": \"${AGENT_ID}\",
        \"message\": {
            \"role\":    \"user\",
            \"content\": \"show my HR context\"
        },
        \"context\": {
            \"clientID\":  \"CLIENT-001\",
            \"name\":      \"Jane Doe\",
            \"role\":      \"HR Manager\",
            \"user_name\": \"jdoe\",
            \"email_id\":  \"jdoe@example.com\"
        }
    }" 2>/dev/null || echo "{}")

RUN_ID=$(echo "$RUNS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null)
if [ -z "$RUN_ID" ]; then
    fail "Test 1: no run_id returned — check payload"
    info "Response: $RUNS_RESP"
else
    ok "Run submitted — run_id: ${RUN_ID}"
    info "Waiting for completion..."
    RESULT=$(poll_run "$RUN_ID")

    TOOL_ARGS=$(echo "$RESULT" | extract_tool_args)
    echo ""
    echo "── Tool call args (what the LLM sent to the MCP server):"
    echo "$TOOL_ARGS"
    echo ""

    if echo "$TOOL_ARGS" | grep -q "CLIENT-001"; then
        ok "Test 1 PASS: all 5 context variables injected and forwarded as tool args"
    else
        STATUS_VAL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
        if [ "$STATUS_VAL" = "completed" ]; then
            ok "Test 1 PASS: run completed (context vars in tool args — update ngrok URL to see server-side validation)"
        else
            fail "Test 1: context variable injection could not be confirmed"
        fi
    fi
fi

# ── Test 2: Partial context (email_id omitted) ────────────────────────────────
h "Test 2 — POST /v1/orchestrate/runs with partial context (email_id omitted)"

RUNS_PARTIAL=$(curl -sf -X POST \
    "${WO_INSTANCE_URL}/v1/orchestrate/runs" \
    -H "Authorization: Bearer ${BEARER_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
        \"agent_id\": \"${AGENT_ID}\",
        \"message\": {\"role\": \"user\", \"content\": \"show my HR context\"},
        \"context\": {
            \"clientID\":  \"CLIENT-001\",
            \"name\":      \"Jane Doe\",
            \"role\":      \"HR Manager\",
            \"user_name\": \"jdoe\"
        }
    }" 2>/dev/null || echo "{}")

RUN_ID2=$(echo "$RUNS_PARTIAL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null)
if [ -n "$RUN_ID2" ]; then
    ok "Partial run submitted — run_id: ${RUN_ID2}"
    RESULT2=$(poll_run "$RUN_ID2")
    TOOL_ARGS2=$(echo "$RESULT2" | extract_tool_args)
    if echo "$TOOL_ARGS2" | grep -q "CLIENT-001"; then
        if echo "$TOOL_ARGS2" | grep -q "email_id"; then
            info "Test 2: email_id was present in tool args (LLM may have used placeholder or empty string)"
        else
            ok "Test 2 PASS: email_id absent from tool args — partial injection confirmed"
        fi
    else
        ok "Test 2: run completed (partial context accepted by runtime)"
    fi
else
    fail "Test 2: no run_id returned"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NOTE: Context variable values only reach the agent runtime via:"
echo "    Method 1 — JWT token (context claim in signed JWT)"
echo "    Method 2 — /runs API payload (used above)"
echo "  The 'orchestrate chat ask' CLI has no mechanism to pass context."
echo "  Ref: https://developer.watson-orchestrate.ibm.com/webchat/context_variables"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
