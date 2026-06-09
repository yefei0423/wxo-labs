#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${SCRIPT_DIR}/tools/get_pdf_download_with_bytes.py"
AGENT="${SCRIPT_DIR}/agents/pdf_bytes_download_agent.yaml"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  download_file_and_stream — deploy pdf_bytes_download_agent → WxO"
echo "  Author: Markus van Kempen | mvk@ca.ibm.com"
echo "  Research | Floor 7½ 🏢🤏 — https://pages.github.ibm.com/mvankempen/homepage/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
command -v orchestrate >/dev/null || { echo "Install WxO orchestrate CLI."; exit 1; }
orchestrate tools import --file "$TOOL" --kind python
orchestrate agents import --file "$AGENT"
orchestrate agents deploy -n pdf_bytes_download_agent
echo "✅ Deploy complete → run ./run_e2e_test.sh or ./run_all.sh"
