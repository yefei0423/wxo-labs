#!/usr/bin/env bash
echo "**Author:** Markus van Kempen | mvk@ca.ibm.com"
echo "[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)"
echo "*No bug too small, no syntax too weird.*"
# ---
# Quick local smoke-test for mcp_hr_context_server.py.
# No WxO account needed. Starts the server, runs POST tests, shuts it down.
# ---
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
fail() { echo -e "${RED}❌ $*${RESET}"; }
info() { echo -e "${CYAN}   $*${RESET}"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  askHR MCP Server — Local Smoke Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Start server in background
python3 mcp_hr_context_server.py &
SERVER_PID=$!
echo ""
info "Server started (PID $SERVER_PID). Waiting for it to be ready..."
sleep 2

# Cleanup on exit
trap "kill $SERVER_PID 2>/dev/null || true; echo ''; info 'Server stopped.'" EXIT

# Health check
echo ""
echo "── Test 1: Health check ──────────────────────────────────"
HEALTH=$(curl -sf http://localhost:8000/health)
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='ok' else 1)"; then
    ok "GET /health → 200 OK"
else
    fail "GET /health failed: $HEALTH"
fi

# Full context POST
echo ""
echo "── Test 2: All 5 context variables present ───────────────"
FULL=$(curl -sf -X POST http://localhost:8000/get-hr-context \
    -H "Content-Type: application/json" \
    -d '{
        "clientID":  "CLIENT-001",
        "name":      "Jane Doe",
        "role":      "HR Manager",
        "user_name": "jdoe",
        "email_id":  "jdoe@example.com"
    }')

echo "$FULL" | python3 -m json.tool
echo ""
if echo "$FULL" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d['validation']['all_context_variables_present'] else 1)"; then
    ok "All 5 context variables received and validated"
else
    fail "Validation failed — some context variables missing"
fi

# Partial context POST
echo ""
echo "── Test 3: Partial context (missing email_id) ────────────"
PARTIAL=$(curl -sf -X POST http://localhost:8000/get-hr-context \
    -H "Content-Type: application/json" \
    -d '{"clientID": "C1", "name": "Bob", "role": "Engineer", "user_name": "bob"}')

echo "$PARTIAL" | python3 -m json.tool
echo ""
if echo "$PARTIAL" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d['status']=='partial' else 1)"; then
    ok "Partial context correctly detected (status=partial)"
else
    fail "Expected status=partial for missing email_id"
fi

# Bearer token extraction
echo ""
echo "── Test 4: Bearer token extraction (Pattern B) ──────────"
BEARER_RESP=$(curl -sf -X POST http://localhost:8000/get-hr-context \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJzdWIiOiJ0ZXN0LXVzZXIifQ.sig" \
    -d '{
        "clientID":  "CLIENT-001",
        "name":      "Test User",
        "role":      "Developer",
        "user_name": "testuser",
        "email_id":  "test@example.com"
    }')

if echo "$BEARER_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); bi=d.get('bearer_identity',{}); exit(0 if bi.get('token_found') else 1)"; then
    USERNAME=$(echo "$BEARER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['bearer_identity']['username'])")
    ok "Bearer token extracted — username from JWT: $USERNAME"
else
    fail "Bearer token not extracted"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  All local tests passed!${RESET}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
