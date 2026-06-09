#!/usr/bin/env bash
# ==============================================================================
# Complete E2E Test Runner: Mock Service + ngrok + WxO Deployment
# ==============================================================================
# **Author:** Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                   SSO E2E Test - Complete Runner                           ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed"
    exit 1
fi

if ! command -v ngrok &> /dev/null; then
    echo "❌ Error: ngrok is not installed"
    echo "📥 Install: brew install ngrok (macOS) or visit https://ngrok.com/download"
    exit 1
fi

echo "✅ Prerequisites OK"
echo ""

# Display SAML endpoints
echo "📋 Your WxO SAML Endpoints:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 find_saml_endpoints.py
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if user wants to proceed
echo "⚠️  This test requires:"
echo "   1. Microsoft Entra ID configured with above SAML endpoints"
echo "   2. Federation Metadata XML from Entra ID"
echo ""
read -p "Have you configured Entra ID? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "📖 Please configure Entra ID first:"
    echo "   1. Go to Microsoft Entra Admin Center"
    echo "   2. Create Enterprise Application (Non-gallery)"
    echo "   3. Configure SAML with the endpoints shown above"
    echo "   4. Download Federation Metadata XML"
    echo ""
    echo "Then run this script again."
    exit 0
fi

echo ""
echo "🚀 Starting test sequence..."
echo ""

# Start mock service in background
echo "1️⃣  Starting mock identity service..."
python3 mock_identity_service.py > mock_service.log 2>&1 &
MOCK_PID=$!
echo "   ✅ Mock service started (PID: $MOCK_PID)"
sleep 2

# Start ngrok in background
echo "2️⃣  Starting ngrok tunnel..."
ngrok http 5000 --log=stdout > ngrok.log 2>&1 &
NGROK_PID=$!
echo "   ✅ ngrok started (PID: $NGROK_PID)"
sleep 3

# Extract ngrok URL
echo "3️⃣  Extracting ngrok URL..."
NGROK_URL=""
for i in {1..10}; do
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o 'https://[^"]*\.ngrok-free\.app' | head -1 || true)
    if [[ -n "$NGROK_URL" ]]; then
        break
    fi
    sleep 1
done

if [[ -z "$NGROK_URL" ]]; then
    echo "   ❌ Failed to get ngrok URL"
    kill $MOCK_PID $NGROK_PID 2>/dev/null || true
    exit 1
fi

echo "   ✅ ngrok URL: $NGROK_URL"
echo ""

# Run the E2E test
echo "4️⃣  Running WxO deployment..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./run_sso_e2e_test.sh "$NGROK_URL"
TEST_RESULT=$?
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up..."
    kill $MOCK_PID 2>/dev/null || true
    kill $NGROK_PID 2>/dev/null || true
    echo "   ✅ Services stopped"
}

trap cleanup EXIT

# Show results
echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                            Test Results                                    ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Status: $([ $TEST_RESULT -eq 0 ] && echo '✅ SUCCESS' || echo '⚠️  PARTIAL')"
echo ""
echo "📝 Logs:"
echo "   - Mock Service: $SCRIPT_DIR/mock_service.log"
echo "   - ngrok:        $SCRIPT_DIR/ngrok.log"
echo ""
echo "🔗 URLs:"
echo "   - Mock Service: $NGROK_URL"
echo "   - ngrok Admin:  http://localhost:4040"
echo ""
echo "📋 Next Steps:"
echo ""
if [[ $TEST_RESULT -eq 0 ]]; then
    echo "   ✅ Deployment successful!"
    echo ""
    echo "   To complete SSO configuration:"
    echo "   1. Configure the connection with Entra metadata:"
    echo "      orchestrate connections configure -a entra-id-sso-app \\"
    echo "        -k oauth_auth_code_flow --sso True \\"
    echo "        -e metadata_url=YOUR_ENTRA_METADATA_XML_URL"
    echo ""
    echo "   2. Test the agent:"
    echo "      orchestrate chat ask -n sso_identity_verifier_agent \"Who am I?\""
else
    echo "   ⚠️  Deployment completed with warnings"
    echo "   Check the logs above for details"
fi
echo ""
echo "Press Enter to stop services and exit..."
read

exit $TEST_RESULT

# Made by Research | 7 1/2 Floor
