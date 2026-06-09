#!/bin/bash
# WxO Intelligence Vault - Unified Deployment & Test
# Author: Markus van Kempen | mvk@ca.ibm.com

echo "🚀 Starting Intelligence Vault Deployment..."

# 1. Start Receiver (Port 5002)
lsof -ti:5002 | xargs kill -9 || true
python3 log_receiver.py > log_server.out 2>&1 &
echo "✅ Log Receiver started on port 5002."

# 2. Deploy to Orchestrate
./deploy_to_new_instance.sh

# 3. Verify Pipeline
echo "🧪 Running Pipeline Verification..."
sleep 2
python3 simulate_logging.py

echo "------------------------------------------------"
echo "✅ DEPLOYMENT COMPLETE"
echo "📂 Live Vault: http://localhost:5002"
echo "📂 Report: log_report.html"
echo "------------------------------------------------"
