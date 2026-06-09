#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
#
# E2E smoke: HTTPS PRIMARY markers (default tool: no huge data: blob — Groq-safe).
# Optional: PDF_DOWNLOAD_INCLUDE_DATA_URI=1 on deployed tool restores base64 in output.
# Optional: E2E_SHOW_HTML=0 to hide the HTML line dump.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'
NAME="pdf_bytes_download_agent"
fail() { echo -e "${RED}FAIL:${RESET} $*"; exit 1; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  download_file_and_stream — E2E: $NAME (orchestrate chat ask -n)"
echo "  Author: Markus van Kempen | mvk@ca.ibm.com"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
command -v orchestrate >/dev/null || fail "orchestrate CLI missing."

OUT="$(echo "q" | orchestrate chat ask -n "$NAME" "Give me the HTTPS download link for the Mozilla PDF.js sample PDF." 2>&1 || true)"

if echo "$OUT" | grep -qE 'data:application/pdf;base64,'; then
  echo -e "${GREEN}✅ data:application/pdf;base64 in output (embedded bytes)${RESET}"
elif echo "$OUT" | grep -qiE 'Same PDF via HTTPS|Plain URL:|mozilla\.github\.io/pdf\.js.*tracemonkey|compressed\.tracemonkey-pldi-09\.pdf'; then
  echo -e "${GREEN}✅ HTTPS fallback / Plain URL markers present (WxO often does not linkify long data: anchors)${RESET}"
elif echo "$OUT" | grep -qE '<a\s|download="|pdfDataDownload'; then
  echo -e "${GREEN}✅ HTML <a …> markers present (base64 may wrap/truncate — check excerpt)${RESET}"
elif echo "$OUT" | grep -qi 'get_pdf_download_with_bytes'; then
  echo -e "${GREEN}✅ Tool name present (CLI may truncate long data: URLs)${RESET}"
else
  fail "Expected data / HTTPS fallback / anchor hints / tool name in assistant output."
fi

if [ "${E2E_SHOW_HTML:-1}" != "0" ]; then
  echo ""
  echo -e "${CYAN}—— HTML / data URL lines from CLI stdout (grep) ——${RESET}"
  echo "$OUT" | grep -E '<a\s|download="|data:application/pdf;base64,|href="|pdfDataDownload|Plain URL:|Same PDF via HTTPS|embedded|Public sample PDF|Download PDF|get_pdf_download_with_bytes' || true
  echo -e "${CYAN}————————————————————————————————————————————————${RESET}"
fi

echo ""
echo -e "${GREEN}E2E CLI smoke PASSED${RESET}"
