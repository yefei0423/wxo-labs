#!/bin/bash
echo "**Author:** Markus van Kempen | mvk@ca.ibm.com"
echo "[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)"
echo "*No bug too small, no syntax too weird.*"

# Move to the script directory
cd "$(dirname "$0")"

echo "🧪 Starting MCP User Context Test..."

# Check if mcp is installed
if ! python -c "import mcp" &> /dev/null; then
    echo "📦 Installing MCP Python SDK..."
    pip install mcp
fi

# Run the simulation
python simulated_orchestrate_client.py

echo -e "\n✅ Test Complete."
