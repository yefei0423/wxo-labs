#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# Research | Floor 7½ 🏢🤏 — https://pages.github.ibm.com/mvankempen/homepage/
# No bug too small, no syntax too weird.
#
# Deploy stub tool + agent to the active Watsonx Orchestrate environment.
#
# Prerequisites:
#   - orchestrate on PATH
#   - orchestrate env activate <env>
#
# What it runs:
#   orchestrate tools import -k python -f tools/ragas_kb_stub.py -r tools/requirements.txt
#   orchestrate agents import -f agents/ragas_stub_agent.yaml
#
# Outputs:
#   Tool ragas_retrieve_stub, agent ragas_rag_stub_agent on the instance.
# Exit:
#   Non-zero if orchestrate missing or import fails.
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/script_banner.sh"
ragas_rag_eval_print_banner

if ! command -v orchestrate >/dev/null 2>&1; then
  echo "Install the Orchestrate CLI / ADK so 'orchestrate' is on PATH." >&2
  exit 1
fi

echo "==> Import Python tool (ragas_retrieve_stub)"
orchestrate tools import -k python -f tools/ragas_kb_stub.py -r tools/requirements.txt

echo "==> Import native agent (ragas_rag_stub_agent)"
orchestrate agents import -f agents/ragas_stub_agent.yaml

echo ""
echo "Done. Quick checks:"
echo "  orchestrate chat ask -n ragas_rag_stub_agent \"What is AskHR?\""
echo "  python probe_retrieval_sources.py --agent-name ragas_rag_stub_agent --prompt \"What is AskHR?\""
