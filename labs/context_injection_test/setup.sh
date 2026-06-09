#!/bin/bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.


echo "Loading Context Injection Test Scenario into WxO..."

# 1. Import the python tool (single-file mode with requirements.txt)
echo "Importing read_user_email python tool..."
orchestrate tools import -k python -f context_test_tool.py -r requirements.txt 2>&1

# 2. Create the Agent
echo "Building context_test_agent..."
orchestrate agents create --name "context_test_agent" \
  --description "Tests the runtime context injection workaround." \
  --tools read_user_email \
  --context-variable wxo_email_id \
  --instructions "You are a test agent. Whenever the user says 'TEST', you must invoke read_user_email and tell them their email."

echo "Setup complete! Test the architecture by running:"
echo "orchestrate chat ask -n context_test_agent"
