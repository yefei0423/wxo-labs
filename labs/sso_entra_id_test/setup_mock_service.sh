#!/usr/bin/env bash
# ==============================================================================
# Setup Script: Mock Identity Service with ngrok
# ==============================================================================
# **Author:** Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔧 Setting up SSO Mock Identity Service..."
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed"
    exit 1
fi

# Check if ngrok is available
if ! command -v ngrok &> /dev/null; then
    echo "⚠️  Warning: ngrok is not installed"
    echo "📥 Install ngrok from: https://ngrok.com/download"
    echo "   Or use: brew install ngrok (on macOS)"
    echo ""
    read -p "Do you want to continue without ngrok? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -q -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1️⃣  Start the mock service in one terminal:"
echo "   cd $SCRIPT_DIR"
echo "   python3 mock_identity_service.py"
echo ""
echo "2️⃣  In another terminal, expose it with ngrok:"
echo "   ngrok http 5000"
echo ""
echo "3️⃣  Copy the ngrok URL (e.g., https://xxxx.ngrok-free.app)"
echo ""
echo "4️⃣  Run the E2E test with that URL:"
echo "   ./run_sso_e2e_test.sh https://xxxx.ngrok-free.app"
echo ""

# Made by Research | 7 1/2 Floor
