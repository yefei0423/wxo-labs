#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
#
# Run the full smoke from THIS directory only: local urllib demo → deploy → orchestrate chat E2E.
# Usage:
#   ./run_all.sh                 # local demo + deploy + run_e2e_test.sh
#   ./run_all.sh --no-demo       # skip local demo (no network needed for that step)
#   ./run_all.sh --deploy-only   # deploy only (no local demo, no E2E)
#   ./run_all.sh --e2e-only      # E2E only (no local demo, no deploy)
#   ./run_all.sh --help          # usage
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SKIP_DEMO=0
DO_DEPLOY=1
DO_E2E=1

while [[ $# -gt 0 ]]; do
  case "${1:-}" in
    --no-demo|--skip-demo) SKIP_DEMO=1 ;;
    --deploy-only) DO_E2E=0; SKIP_DEMO=1 ;;
    --e2e-only) DO_DEPLOY=0; SKIP_DEMO=1 ;;
    -h|--help)
      cat <<'HELP'
Usage: ./run_all.sh [options]

  (default)   Local urllib demo → deploy_to_wxo.sh → run_e2e_test.sh
  --no-demo   Skip examples/streaming_pdf_fetch_demo.py
  --deploy-only   Deploy only (skips local demo + E2E)
  --e2e-only      Only run_e2e_test.sh (skips local demo + deploy)

Run from: download_file_and_stream_e2e_test/
HELP
      exit 0
      ;;
    *)
      echo "Unknown option: $1 — try --help" >&2
      exit 1
      ;;
  esac
  shift
done

TOTAL=0
[[ $SKIP_DEMO -eq 0 ]] && TOTAL=$((TOTAL + 1))
[[ $DO_DEPLOY -eq 1 ]] && TOTAL=$((TOTAL + 1))
[[ $DO_E2E -eq 1 ]] && TOTAL=$((TOTAL + 1))

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  download_file_and_stream_e2e_test — full run · cwd=$(pwd)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

N=0

if [[ $SKIP_DEMO -eq 0 ]]; then
  N=$((N + 1))
  echo ""
  echo "=== [$N/$TOTAL] Local chunked HTTP demo (examples/streaming_pdf_fetch_demo.py · no WxO CLI)"
  python3 "${SCRIPT_DIR}/examples/streaming_pdf_fetch_demo.py"
  echo "✅ Local demo OK"
fi

if [[ $DO_DEPLOY -eq 1 ]]; then
  N=$((N + 1))
  echo ""
  echo "=== [$N/$TOTAL] Deploy tool + pdf_bytes_download_agent → WxO ==="
  bash "${SCRIPT_DIR}/deploy_to_wxo.sh"
fi

if [[ $DO_E2E -eq 1 ]]; then
  N=$((N + 1))
  echo ""
  echo "=== [$N/$TOTAL] E2E: orchestrate chat ask (-n pdf_bytes_download_agent)"
  bash "${SCRIPT_DIR}/run_e2e_test.sh"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Finished (${TOTAL} step(s))."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
