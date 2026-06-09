#!/bin/bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.


echo "Loading Financial Tool with Input Defaults into WxO..."

# 1. Import the python tool
echo "Importing financial_tool python tools..."
orchestrate tools import --kind python -f financial_tool.py

# 2. Create the Agent
echo "Building financial_impact_agent..."
orchestrate agents create --name "financial_impact_agent" \
  --description "Tests tool input defaulting and Pydantic schema validation." \
  --tools calculate_net_impact --tools get_default_financial_settings --tools financial_impact_selection \
  --instructions "You help users assess financial impacts. If they don't provide an amount, assume the default from the tool."

echo "Setup complete!"
echo "To test default: orchestrate chat ask -n financial_impact_agent 'Run calculations without providing an amount'"
echo "To test explicit: orchestrate chat ask -n financial_impact_agent 'Calculate impact for 500 dollars'"
