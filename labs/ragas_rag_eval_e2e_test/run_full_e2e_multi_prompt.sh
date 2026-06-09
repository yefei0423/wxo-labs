#!/usr/bin/env bash
# Author: Markus van Kempen | mvk@ca.ibm.com
# Research | Floor 7½ 🏢🤏 — https://pages.github.ibm.com/mvankempen/homepage/
# No bug too small, no syntax too weird.
#
# One-shot multi-prompt E2E: optional deploy → for each question, REST chat + trace poll +
# context extraction. By default runs Ragas (context_precision / context_recall) when a judge
# backend is configured (OPENAI_API_KEY or watsonx env — see ragas_eval_backends + README).
#
# Prerequisites:
#   orchestrate env activate <env>   # JWT for wxo_helpers / chat API
#   pip: requirements.txt (+ requirements-ragas-watsonx.txt for watsonx judge)
#
# Usage:
#   ./run_full_e2e_multi_prompt.sh
#   RUN_RAGAS=0 ./run_full_e2e_multi_prompt.sh          # collect contexts only (--no-ragas)
#   SKIP_DEPLOY=1 ./run_full_e2e_multi_prompt.sh
#   PROMPTS_FILE=./my_questions.txt GROUND_TRUTHS_FILE=./my_refs.txt ./run_full_e2e_multi_prompt.sh
#   DUMP_JSON=1 ./run_full_e2e_multi_prompt.sh
#   RUN_VALIDATE=1 ./run_full_e2e_multi_prompt.sh       # extra chat per prompt (e2e_validate)
#   RUN_RAGAS_ON_LAST=1 RUN_RAGAS=0 RAGAS_GROUND_TRUTH="..." ./run_full_e2e_multi_prompt.sh
#       # legacy: score only the last prompt (RUN_RAGAS must be 0)
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

AGENT_NAME="${AGENT_NAME:-ragas_rag_stub_agent}"
PROMPTS_FILE="${PROMPTS_FILE:-${ROOT}/e2e_prompts_default.txt}"
GROUND_TRUTHS_FILE="${GROUND_TRUTHS_FILE:-${ROOT}/e2e_ground_truths_default.txt}"
SKIP_DEPLOY="${SKIP_DEPLOY:-0}"
DUMP_JSON="${DUMP_JSON:-0}"
RUN_VALIDATE="${RUN_VALIDATE:-0}"
# Default: run Ragas on every prompt (set RUN_RAGAS=0 for --no-ragas only).
RUN_RAGAS="${RUN_RAGAS:-1}"
RUN_RAGAS_ON_LAST="${RUN_RAGAS_ON_LAST:-0}"
RAGAS_GROUND_TRUTH_FALLBACK="${RAGAS_GROUND_TRUTH:-}"
RAGAS_BACKEND="${RAGAS_BACKEND:-auto}"

# Optional: pass-through to e2e_validate_rag_turn.py (quote carefully).
VALIDATE_EXTRA=( )
# Example: VALIDATE_EXTRA=( --answer-must-contain "AskHR" --tool-must-call ragas_retrieve_stub )

OUT_DIR="${OUT_DIR:-${ROOT}/e2e_multi_run_logs}"
mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
SUMMARY_LOG="${OUT_DIR}/summary_${STAMP}.log"

log() { echo "$*" | tee -a "${SUMMARY_LOG}"; }

failures=0
prompts=()
ground_truths=()

load_prompts() {
  prompts=()
  if [[ -f "$PROMPTS_FILE" ]]; then
    while IFS= read -r line || [[ -n "${line:-}" ]]; do
      [[ -z "${line// }" ]] && continue
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      prompts+=("$line")
    done < "$PROMPTS_FILE"
  fi
  if [[ ${#prompts[@]} -eq 0 ]]; then
    log "No prompts in ${PROMPTS_FILE:-}(missing file?). Using two built-in AskHR lines."
    prompts=(
      "What is AskHR, and what objectives does the documentation mention?"
      "What HR topics does the AskHR assistant documentation cover?"
    )
  fi
}

load_ground_truths() {
  ground_truths=()
  [[ -f "$GROUND_TRUTHS_FILE" ]] || return 0
  while IFS= read -r line || [[ -n "${line:-}" ]]; do
    [[ -z "${line// }" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    ground_truths+=("$line")
  done < "$GROUND_TRUTHS_FILE"
}

pipeline_no_ragas=( python3 wxo_rag_ragas_pipeline.py --agent-name "$AGENT_NAME" --split-passages --no-ragas )
[[ "${DUMP_JSON}" == "1" ]] && pipeline_no_ragas+=( --dump-json )

ground_truth_for_index() {
  # $1 = 1-based index
  local idx="$1"
  local per_gt="${RAGAS_GROUND_TRUTH_FALLBACK}"
  if [[ ${#ground_truths[@]} -ge "$idx" && "$idx" -ge 1 ]]; then
    per_gt="${ground_truths[$((idx - 1))]}"
  fi
  printf '%s' "$per_gt"
}

run_pipeline_with_ragas() {
  local prompt="$1"
  local idx="$2"
  local per_log="$3"
  local gt
  gt="$(ground_truth_for_index "$idx")"
  local py=( python3 wxo_rag_ragas_pipeline.py --agent-name "$AGENT_NAME" --split-passages --prompt "$prompt" --ragas-backend "$RAGAS_BACKEND" )
  [[ "${DUMP_JSON}" == "1" ]] && py+=( --dump-json )
  [[ -n "${gt// }" ]] && py+=( --ground-truth "$gt" )
  "${py[@]}" 2>&1 | tee "$per_log"
}

{
  log "Author: Markus van Kempen | mvk@ca.ibm.com"
  log "Research | Floor 7½ 🏢🤏 — https://pages.github.ibm.com/mvankempen/homepage/"
  log "No bug too small, no syntax too weird."
  log ""
  log "=== run_full_e2e_multi_prompt.sh ==="
  log "Started: $(date -Iseconds)"
  log "Agent: ${AGENT_NAME}"
  log "Prompts file: ${PROMPTS_FILE}"
  log "GROUND_TRUTHS_FILE: ${GROUND_TRUTHS_FILE:-none}"
  log "RUN_RAGAS: ${RUN_RAGAS}  RUN_RAGAS_ON_LAST: ${RUN_RAGAS_ON_LAST}"
  log "RAGAS_BACKEND: ${RAGAS_BACKEND}"
  log "OUT_DIR: ${OUT_DIR}"
  log ""

  if [[ "${SKIP_DEPLOY}" != "1" ]]; then
    log "==> ./deploy.sh"
    ./deploy.sh
  else
    log "==> SKIP_DEPLOY=1 — skipping deploy"
  fi

  load_prompts
  load_ground_truths
  n="${#prompts[@]}"
  log "Loaded ${n} prompt(s), ${#ground_truths[@]} ground-truth line(s) (excluding comments)."
  log ""

  i=0
  for prompt in "${prompts[@]}"; do
    i=$((i + 1))
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Prompt ${i}/${n}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    per_log="${OUT_DIR}/prompt_${STAMP}_${i}.log"

    use_ragas=0
    if [[ "${RUN_RAGAS}" == "1" ]]; then
      use_ragas=1
    elif [[ "${RUN_RAGAS_ON_LAST}" == "1" && "$i" -eq "$n" ]]; then
      use_ragas=1
    fi

    if [[ "$use_ragas" -eq 1 ]]; then
      log "==> wxo_rag_ragas_pipeline.py + Ragas (judge: ${RAGAS_BACKEND})"
      if run_pipeline_with_ragas "$prompt" "$i" "$per_log"; then
        log "OK — log: $per_log"
      else
        log "FAIL — log: $per_log"
        failures=$((failures + 1))
      fi
    else
      log "==> wxo_rag_ragas_pipeline.py --no-ragas"
      if "${pipeline_no_ragas[@]}" --prompt "$prompt" 2>&1 | tee "$per_log"; then
        log "OK — log: $per_log"
      else
        log "FAIL — log: $per_log"
        failures=$((failures + 1))
      fi
    fi

    if [[ "${RUN_VALIDATE}" == "1" ]]; then
      log "==> e2e_validate_rag_turn.py (extra chat for this prompt)"
      if python3 e2e_validate_rag_turn.py --agent-name "$AGENT_NAME" --prompt "$prompt" "${VALIDATE_EXTRA[@]}" 2>&1 | tee -a "$per_log"; then
        log "VALIDATE PASS"
      else
        log "VALIDATE FAIL"
        failures=$((failures + 1))
      fi
    fi
    log ""
  done

  log "Finished: $(date -Iseconds)"
  if [[ "$failures" -eq 0 ]]; then
    log "OVERALL: OK (${n} prompt run(s))"
  else
    log "OVERALL: FAIL (${failures} failed step(s); see logs under ${OUT_DIR})"
  fi
} 2>&1

if [[ "$failures" -ne 0 ]]; then
  exit 1
fi
exit 0
