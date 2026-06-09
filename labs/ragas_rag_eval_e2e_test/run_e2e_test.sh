#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# Research | Floor 7½ 🏢🤏 — https://pages.github.ibm.com/mvankempen/homepage/
# No bug too small, no syntax too weird.
#
# Convenience wrapper: activate .venv if it exists, then run e2e_validate_rag_turn.py.
#
# Prerequisites:
#   - orchestrate env activate <env>  (JWT for REST)
#   - pip install -r requirements.txt in this directory or .venv
#
# Usage:
#   ./run_e2e_test.sh
#   ./run_e2e_test.sh --agent-name ragas_rag_stub_agent --prompt "..." 
# All extra args are passed through to e2e_validate_rag_turn.py (--help for options).
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/script_banner.sh"
ragas_rag_eval_print_banner

if [[ -d .venv ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

exec python e2e_validate_rag_turn.py "$@"
