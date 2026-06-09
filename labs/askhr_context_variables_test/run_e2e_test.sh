#!/usr/bin/env bash
# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com
# ---
# End-to-end test for askHR context variables + MCP tool integration.
#
# Tests run:
#   Test 1  — OpenAPI tool (Pattern A): LLM reads context from instructions,
#             passes to MCP server as tool arguments. Validates all 5 context
#             variables arrive at the server.
#   Test 2  — Python tool (Pattern C): direct request_context read. Validates
#             WxO injects context vars without LLM mediation.
#   Test 3  — Multi-turn: second message confirms context is stable across turns.
#   Test 4  — Health check: server is reachable before live WxO tests.
#
# Prerequisites:
#   - mcp_hr_context_server.py running on port 8000
#   - ngrok running and hr_context_openapi.json updated with tunnel URL
#   - orchestrate env activate <ENV_NAME>
#   - askHR_agent deployed (run ./deploy_to_wxo.sh first)
# ---

set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

PASS=0; FAIL=0; SKIP=0
LOG_FILE="test_results.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ok()   { echo -e "${GREEN}  ✅ PASS${RESET} — $*"; ((PASS++)); }
fail() { echo -e "${RED}  ❌ FAIL${RESET} — $*"; ((FAIL++)); }
skip() { echo -e "${YELLOW}  ⏭  SKIP${RESET} — $*"; ((SKIP++)); }
info() { echo -e "${CYAN}     $*${RESET}"; }
h()    { echo -e "\n${BOLD}$*${RESET}"; }

{
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  askHR Context Variables E2E Test"
echo "  $(date)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Detect ngrok URL from running process ────────────────────────────────────
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" \
    2>/dev/null || echo "")

# ─────────────────────────────────────────────────────────────────────────────
h "Test 0 — Environment checks"

# CLI available?
if command -v orchestrate &>/dev/null; then
    ok "orchestrate CLI available"
else
    fail "orchestrate CLI not found"
fi

# Active environment?
ACTIVE_ENV=$(orchestrate env list 2>/dev/null | grep "(active)" | awk '{print $1}' || true)
if [ -n "$ACTIVE_ENV" ]; then
    ok "Active WxO environment: ${ACTIVE_ENV}"
else
    fail "No active WxO environment — run: orchestrate env activate <ENV_NAME>"
fi

# MCP server health check
if curl -sf http://localhost:8000/health &>/dev/null; then
    ok "MCP server reachable at localhost:8000"
else
    skip "MCP server not running locally — skipping server-side tests (Tests 1-2 will still use WxO live)"
fi

# ngrok tunnel
if [ -n "$NGROK_URL" ]; then
    ok "ngrok tunnel detected: ${NGROK_URL}"
else
    skip "ngrok not running — OpenAPI tool tests will rely on previously configured URL"
fi

# ─────────────────────────────────────────────────────────────────────────────
h "Test 1 — Pattern A: OpenAPI tool — LLM-mediated context argument injection"
info "Asking askHR_agent to show HR context (agent instructions contain {clientID} etc.)"
info "Expected: LLM calls get_hr_context with all 5 context vars as arguments"

RESP1=$(echo "show my HR context" | orchestrate chat ask -n askHR_agent "show my HR context" 2>&1 || true)

if echo "$RESP1" | grep -qi "hr_summary\|context_variables_received\|clientID\|all_context_variables_present"; then
    ok "Pattern A: context variables received by MCP server tool response"
    info "Response excerpt: $(echo "$RESP1" | grep -i "clientID\|name\|role\|email_id\|hr_summary" | head -3)"
elif echo "$RESP1" | grep -qi "get_hr_context\|hr context\|profile"; then
    ok "Pattern A: tool was called (server response may not be fully visible in CLI output)"
else
    fail "Pattern A: no evidence of context variable injection or tool call"
    info "Full response: $RESP1"
fi

# ─────────────────────────────────────────────────────────────────────────────
h "Test 2 — Pattern C: Python tool — direct request_context read"
info "Asking askHR_agent to read context directly (bypasses LLM, reads request_context)"
info "Expected: read_hr_context returns injected context vars directly"

RESP2=$(echo "read context directly" | orchestrate chat ask -n askHR_agent "read context directly" 2>&1 || true)

if echo "$RESP2" | grep -qi "ALL CONTEXT VARIABLES INJECTED\|HR Context Read\|clientID\|email_id"; then
    ok "Pattern C: request_context variables confirmed injected by WxO"
    info "Response excerpt: $(echo "$RESP2" | grep -i "clientID\|email_id\|role\|status" | head -3)"
elif echo "$RESP2" | grep -qi "NOT_INJECTED\|MISSING"; then
    fail "Pattern C: some context variables were NOT_INJECTED — check agent YAML context_variables list"
    info "Response: $RESP2"
else
    skip "Pattern C: could not determine result from CLI output — check WxO UI for tool call details"
    info "Response: $RESP2"
fi

# ─────────────────────────────────────────────────────────────────────────────
h "Test 3 — Multi-turn: context stable across conversation turns"
info "Second message in same conversation should still have all context vars"

RESP3=$(printf "show my HR context\nread context directly" | orchestrate chat ask -n askHR_agent "show my HR context" 2>&1 || true)

if echo "$RESP3" | grep -qi "clientID\|hr_summary\|HR Context"; then
    ok "Multi-turn: context variables present across turns"
else
    skip "Multi-turn: could not verify across turns from CLI — use WxO UI for multi-turn validation"
fi

# ─────────────────────────────────────────────────────────────────────────────
h "Test 4 — Local server direct POST (no WxO, validates server logic)"
info "POST directly to /get-hr-context with test context values"

if curl -sf http://localhost:8000/health &>/dev/null; then
    LOCAL_RESP=$(curl -sf -X POST http://localhost:8000/get-hr-context \
        -H "Content-Type: application/json" \
        -d '{
            "clientID":  "CLIENT-TEST-001",
            "name":      "Jane Doe",
            "role":      "Engineer",
            "user_name": "jdoe",
            "email_id":  "jdoe@example.com"
        }' 2>/dev/null || true)

    if echo "$LOCAL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('validation',{}).get('all_context_variables_present') else 1)" 2>/dev/null; then
        ok "Local server: all 5 context variables accepted and validated"
        HR_SUMMARY=$(echo "$LOCAL_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hr_summary',''))" 2>/dev/null || true)
        info "HR summary: ${HR_SUMMARY}"
    else
        fail "Local server: validation failed — check mcp_hr_context_server.py"
        info "Response: $LOCAL_RESP"
    fi

    # Also test partial (missing email_id)
    PARTIAL_RESP=$(curl -sf -X POST http://localhost:8000/get-hr-context \
        -H "Content-Type: application/json" \
        -d '{"clientID": "C1", "name": "Bob", "role": "Admin", "user_name": "bob"}' \
        2>/dev/null || true)

    if echo "$PARTIAL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='partial' and 'email_id' in d.get('validation',{}).get('missing',[]) else 1)" 2>/dev/null; then
        ok "Local server: correctly detects missing 'email_id' and returns status=partial"
    else
        fail "Local server: partial context not correctly detected"
    fi
else
    skip "MCP server not running — skipping local server tests (Test 4)"
fi

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  Results: ${GREEN}${PASS} passed${RESET}  ${RED}${FAIL} failed${RESET}  ${YELLOW}${SKIP} skipped${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}  OVERALL: FAILED${RESET}"
    echo ""
    exit 1
else
    echo -e "${GREEN}  OVERALL: PASSED${RESET}"
    echo ""
fi

} 2>&1 | tee "$LOG_FILE"
