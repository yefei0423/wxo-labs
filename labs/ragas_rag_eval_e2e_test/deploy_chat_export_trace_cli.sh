#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# Research | Floor 7½ 🏢🤏 — https://pages.github.ibm.com/mvankempen/homepage/
# No bug too small, no syntax too weird.
#
# Deploy RAG stub agent, run one chat turn (REST) to obtain trace_id, export spans via Orchestrate CLI.
#
# Prerequisites:
#   orchestrate env activate <env>
#   Same IAM as Python wxo_helpers (CLI token cache)
#
# Usage:
#   ./deploy_chat_export_trace_cli.sh
#   AGENT_NAME=my_agent PROMPT="..." SKIP_DEPLOY=1 ./deploy_chat_export_trace_cli.sh
#   SPLIT_PASSAGES=0 ./deploy_chat_export_trace_cli.sh   # single blob per tool return
#   REQUIRE_TOOL_SPANS=0 ./deploy_chat_export_trace_cli.sh   # accept first export (no tool spans)
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source "${ROOT}/script_banner.sh"
ragas_rag_eval_print_banner

AGENT_NAME="${AGENT_NAME:-ragas_rag_stub_agent}"
PROMPT="${PROMPT:-What is AskHR, and what objectives does the documentation mention?}"
OUT_DIR="${OUT_DIR:-${ROOT}/cli_trace_exports}"
EXPORT_RETRIES="${EXPORT_RETRIES:-15}"
EXPORT_DELAY_SEC="${EXPORT_DELAY_SEC:-3}"
SPLIT_PASSAGES="${SPLIT_PASSAGES:-1}"
INITIAL_DELAY_SEC="${INITIAL_DELAY_SEC:-5}"
REQUIRE_TOOL_SPANS="${REQUIRE_TOOL_SPANS:-1}"

if ! command -v orchestrate >/dev/null 2>&1; then
  echo "orchestrate CLI not found on PATH." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

if [[ "${SKIP_DEPLOY:-0}" != "1" ]]; then
  echo "==> Deploy tool + agent (./deploy.sh)"
  ./deploy.sh
else
  echo "==> SKIP_DEPLOY=1 — skipping ./deploy.sh"
fi

echo "==> Chat via API → trace_id (get_trace_id_from_chat.py)"
TRACE_ID="$(python3 get_trace_id_from_chat.py --agent-name "${AGENT_NAME}" --prompt "${PROMPT}")"
echo "    trace_id: ${TRACE_ID}"

OUT_JSON="${OUT_DIR}/trace_${TRACE_ID}.json"
CONTEXTS_JSON="${OUT_DIR}/trace_${TRACE_ID}_contexts.json"

echo "    waiting ${INITIAL_DELAY_SEC}s before export (child spans often land after root)…"
sleep "${INITIAL_DELAY_SEC}"

echo "==> Export spans: orchestrate observability traces export -t ... -o ${OUT_JSON}"

ok=0
for i in $(seq 1 "${EXPORT_RETRIES}"); do
  if orchestrate observability traces export -t "${TRACE_ID}" -o "${OUT_JSON}" --pretty; then
    if [[ -s "${OUT_JSON}" ]]; then
      if [[ "${REQUIRE_TOOL_SPANS}" != "1" ]]; then
        ok=1
        break
      fi
      if python3 -c "from wxo_helpers import cli_trace_export_complete_enough; import sys; sys.exit(0 if cli_trace_export_complete_enough('${OUT_JSON}') else 1)"; then
        ok=1
        break
      fi
      echo "    export OK but trace still partial (waiting for tools.task / ToolMessage); ${i}/${EXPORT_RETRIES}…"
    fi
  else
    echo "    export failed; ${i}/${EXPORT_RETRIES}…"
  fi
  sleep "${EXPORT_DELAY_SEC}"
done

if [[ "${ok}" != "1" ]]; then
  echo "FAILED: no complete export after ${EXPORT_RETRIES} attempts." >&2
  echo "Try: REQUIRE_TOOL_SPANS=0 to keep partial trace, or: orchestrate observability traces search --last 30m -a ${AGENT_NAME} -l 5" >&2
  exit 1
fi

echo "==> Extract ToolMessage contexts → ${CONTEXTS_JSON}"
EXTRACT_FLAGS=()
if [[ "${SPLIT_PASSAGES}" == "1" ]]; then
  EXTRACT_FLAGS+=(--split-passages)
fi
python3 extract_contexts_from_cli_trace.py "${OUT_JSON}" "${EXTRACT_FLAGS[@]}" | tee "${CONTEXTS_JSON}"

echo ""
echo "Done."
echo "  Full trace:     ${OUT_JSON}"
echo "  Contexts JSON:  ${CONTEXTS_JSON}"
echo "  Manual search:  orchestrate observability traces search --last 30m -a ${AGENT_NAME} -l 5"
echo "  Manual export:  orchestrate observability traces export -t ${TRACE_ID} -o trace.json --pretty"
