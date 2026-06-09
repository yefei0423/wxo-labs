#!/usr/bin/env bash
# ==============================================================================
# Get WatsonX Orchestrate Version Information
# ==============================================================================
# **Author:** Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ==============================================================================

set -euo pipefail

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║              WatsonX Orchestrate Version Information                       ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# 1. Get CLI/ADK Version
echo "📦 Orchestrate CLI/ADK Version:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
orchestrate --version | grep "ADK Version" || echo "Unable to determine ADK version"
echo ""

# 2. Get Instance Information
if [[ -f "../../.env" ]]; then
    echo "🌐 Instance Information:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    INSTANCE_URL=$(grep "WO_NEW_INSTANCE_URL=" "../../.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    
    if [[ -n "$INSTANCE_URL" ]]; then
        echo "Instance URL: $INSTANCE_URL"
        
        # Extract region from URL
        if [[ "$INSTANCE_URL" =~ us-south ]]; then
            REGION="US South (Dallas)"
        elif [[ "$INSTANCE_URL" =~ eu-de ]]; then
            REGION="EU Central (Frankfurt)"
        elif [[ "$INSTANCE_URL" =~ eu-gb ]]; then
            REGION="EU GB (London)"
        elif [[ "$INSTANCE_URL" =~ au-syd ]]; then
            REGION="Australia (Sydney)"
        elif [[ "$INSTANCE_URL" =~ dl\.watson-orchestrate ]]; then
            REGION="Development/Trial"
        else
            REGION="Unknown"
        fi
        
        echo "Region: $REGION"
        
        # Extract instance ID
        INSTANCE_ID=$(echo "$INSTANCE_URL" | grep -oE '[0-9]{8}-[0-9]{4}-[0-9]{4}-[0-9a-f]{4}-[0-9a-f]{12}' || echo "Unknown")
        echo "Instance ID: $INSTANCE_ID"
    else
        echo "⚠️  Instance URL not found in .env file"
    fi
    echo ""
fi

# 3. Get Component Versions (from orchestrate --version)
echo "🔧 Component Versions:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
orchestrate --version | grep -E "(SERVER_TAG|WORKER_TAG|UITAG|BUILDER_TAG|AGENT_GATEWAY_TAG)" | head -5
echo ""

# 4. Try to get cloud instance version via API
echo "☁️  Cloud Instance Version (if accessible):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ -f "../../.env" ]]; then
    API_KEY=$(grep "WO_NEW_API_KEY=" "../../.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    INSTANCE_URL=$(grep "WO_NEW_INSTANCE_URL=" "../../.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    
    if [[ -n "$API_KEY" ]] && [[ -n "$INSTANCE_URL" ]]; then
        # Try to get version from observability endpoint
        VERSION_INFO=$(curl -s -H "Authorization: Bearer $API_KEY" \
            "$INSTANCE_URL/v1/observability/health" 2>/dev/null || echo "")
        
        if [[ -n "$VERSION_INFO" ]] && [[ "$VERSION_INFO" != *"unauthorized"* ]]; then
            echo "$VERSION_INFO" | grep -i version || echo "Version info not available in health endpoint"
        else
            echo "⚠️  Unable to access cloud instance version (requires authentication)"
            echo "   You can check the version in the WxO UI: Settings → About"
        fi
    else
        echo "⚠️  API credentials not found in .env file"
    fi
else
    echo "⚠️  .env file not found"
fi
echo ""

# 5. Summary
echo "📋 Summary:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "WatsonX Orchestrate version information:"
echo ""
echo "  📦 CLI/ADK Version: $(orchestrate --version | grep 'ADK Version' | cut -d':' -f2 | xargs)"
echo "  🏷️  Edition: Standard Trial Edition (from UI About page)"
echo "  🌐 Instance CRN: Available in UI Settings → About"
echo ""
echo "Note: WatsonX Orchestrate cloud instances don't expose a single 'version number'."
echo "Instead, each component (server, worker, UI, etc.) has its own build tag."
echo ""
echo "Key component versions (build dates):"
echo "  • Server: $(orchestrate --version | grep 'SERVER_TAG' | cut -d':' -f2 | xargs)"
echo "  • UI: $(orchestrate --version | grep 'UITAG' | cut -d':' -f2 | xargs)"
echo "  • Agent Gateway: $(orchestrate --version | grep 'AGENT_GATEWAY_TAG' | cut -d':' -f2 | xargs)"
echo ""
echo "For full component list: orchestrate --version"
echo "For specific component: orchestrate --version | grep <COMPONENT>_TAG"
echo ""

# Made by Research | 7 1/2 Floor
