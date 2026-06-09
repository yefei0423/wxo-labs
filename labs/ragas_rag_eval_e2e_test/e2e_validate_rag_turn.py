#!/usr/bin/env python3
"""
End-to-end validation: one chat/completions turn + thread inspection.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

Gives a plain-language PASS/FAIL report for operators (answer quality + retrieval signal).

Example (default expects ragas_rag_stub_agent + stub tool output):
  python e2e_validate_rag_turn.py

Custom agent / stricter checks:
  python e2e_validate_rag_turn.py \\
    --agent-name ragas_rag_stub_agent \\
    --answer-must-contain "AskHR,watsonx" \\
    --context-must-contain "[DOC 1,AskHR" \\
    --tool-must-call ragas_retrieve_stub
"""

from __future__ import annotations

import argparse
import time

from wxo_helpers import (
    assistant_answer_from_chat_body,
    candidate_contexts_from_thread_messages,
    chat_completions,
    get_agent_id_by_name,
    get_thread_messages,
    tools_invoked_from_thread_messages,
)


def _split_csv(s: str | None) -> list[str]:
    if not s or not s.strip():
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _contains_all(haystack: str, needles: list[str], *, label: str, errors: list[str]) -> bool:
    hay_l = haystack.lower()
    missing = [n for n in needles if n.lower() not in hay_l]
    if missing:
        errors.append(f"{label} missing terms (case-insensitive): {missing}")
        return False
    return True


def _contexts_cover_terms(contexts: list[str], needles: list[str], errors: list[str]) -> bool:
    if not needles:
        return True
    blob = "\n".join(contexts).lower()
    missing = [n for n in needles if n.lower() not in blob]
    if missing:
        errors.append(
            f"Retrieved/tool context strings did not contain: {missing} "
            f"(extracted {len(contexts)} candidate blob(s); tune wxo_helpers if needed)"
        )
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E: validate one WxO agent turn (answer + retrieval/tool signal)."
    )
    parser.add_argument(
        "--agent-name",
        default="ragas_rag_stub_agent",
        help="Orchestrate agent name (default: ragas_rag_stub_agent).",
    )
    parser.add_argument(
        "--prompt",
        default="What is AskHR, and what objectives does the documentation mention?",
        help="User message for the turn.",
    )
    parser.add_argument(
        "--thread-settle-s",
        type=float,
        default=2.0,
        help="Seconds to wait before GET thread messages (trace persistence).",
    )
    parser.add_argument(
        "--answer-min-len",
        type=int,
        default=80,
        help="Fail if assistant answer is shorter than this (characters).",
    )
    parser.add_argument(
        "--answer-must-contain",
        default="AskHR,watsonx Orchestrate",
        help="Comma-separated substrings that must all appear in the answer (case-insensitive). Empty to skip.",
    )
    parser.add_argument(
        "--context-must-contain",
        default="[DOC 1,leave balance",
        help="Comma-separated substrings; at least one chunk blob from thread should include each (combined). Empty to skip.",
    )
    parser.add_argument(
        "--tool-must-call",
        default="ragas_retrieve_stub",
        help="Tool name that must appear in step_history (empty to skip).",
    )
    parser.add_argument(
        "--no-require-context-blobs",
        dest="require_context_blobs",
        action="store_false",
        help="Allow zero extracted context blobs (e.g. native KB-only agents).",
    )
    parser.set_defaults(require_context_blobs=True)
    args = parser.parse_args()

    answer_terms = _split_csv(args.answer_must_contain)
    context_terms = _split_csv(args.context_must_contain)
    tool_required = (args.tool_must_call or "").strip()

    print("=== Watsonx Orchestrate — RAG-style E2E validation ===\n")
    print(f"Agent: {args.agent_name!r}")
    print(f"Prompt: {args.prompt!r}\n")

    errors: list[str] = []
    warnings: list[str] = []

    try:
        agent_id = get_agent_id_by_name(args.agent_name)
    except ValueError as e:
        print(f"FAIL: {e}")
        print("\nNext step: deploy the agent (see ./deploy.sh) or fix --agent-name.")
        return 1

    body, hdr = chat_completions(agent_id, args.prompt)
    answer = assistant_answer_from_chat_body(body)
    thread_id = body.get("thread_id")

    print("--- HTTP chat/completions ---")
    print(f"thread_id: {thread_id}")
    print(f"trace_id (body): {body.get('trace_id')}")
    print(f"trace_id (header): {hdr.get('trace_id_header')}")
    print(f"Answer length: {len(answer)} chars")
    if answer:
        preview = answer[:500] + ("…" if len(answer) > 500 else "")
        print(f"Answer preview:\n{preview}\n")

    if not thread_id:
        errors.append("Response had no thread_id; cannot validate thread messages.")

    if len(answer) < args.answer_min_len:
        errors.append(
            f"Answer too short ({len(answer)} chars); expected at least {args.answer_min_len}."
        )

    _contains_all(answer, answer_terms, label="Answer", errors=errors)

    tools: list[str] = []
    contexts: list[str] = []
    if thread_id:
        time.sleep(max(0.0, args.thread_settle_s))
        try:
            messages = get_thread_messages(thread_id)
        except Exception as ex:
            errors.append(f"GET thread messages failed: {ex}")
            messages = []
        tools = tools_invoked_from_thread_messages(messages)
        contexts = candidate_contexts_from_thread_messages(messages)

    print("--- Thread inspection ---")
    print(f"Tools invoked (step_history): {tools if tools else '(none detected)'}")
    print(f"Candidate context blobs extracted: {len(contexts)}")
    for i, c in enumerate(contexts[:3]):
        prev = c[:240].replace("\n", " ") + ("…" if len(c) > 240 else "")
        print(f"  [{i}] {prev}")

    if tool_required and tool_required not in tools:
        errors.append(
            f"Expected tool {tool_required!r} to run; got {tools!r}. "
            "Check agent instructions / model behavior."
        )

    if args.require_context_blobs and not contexts:
        errors.append(
            "No candidate retrieval/tool text extracted from thread messages. "
            "For native-KB agents this may be expected — rerun with --no-require-context-blobs."
        )

    _contexts_cover_terms(contexts, context_terms, errors)

    # Human-facing summary
    print("\n" + "=" * 56)
    if errors:
        print("RESULT: FAIL")
        for e in errors:
            print(f"  - {e}")
        if warnings:
            print("\nWarnings:")
            for w in warnings:
                print(f"  - {w}")
        print(
            "\nWhat to do next:\n"
            "  1) Run ./deploy.sh and confirm the agent name matches.\n"
            "  2) Run: orchestrate chat ask -n <agent> \"...\" and verify the model calls your tool.\n"
            "  3) python probe_retrieval_sources.py --agent-name ... --prompt ... --raw-messages\n"
            "  4) Soften checks: --no-require-context-blobs or clear --context-must-contain.\n"
        )
        return 1

    if warnings:
        print("RESULT: PASS (with warnings)")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("RESULT: PASS")

    print(
        "\nWhy this passed:\n"
        "  - The assistant returned a substantive answer.\n"
        "  - Thread messages exposed tool/history text you can treat as Ragas `contexts`.\n"
        "  - Optional substring and tool checks matched your expectations.\n"
    )
    print(
        "Next steps for Ragas:\n"
        "  - Map `contexts` into a HuggingFace Dataset and run evaluate(...) "
        "with context_precision / context_recall.\n"
        "  - See run_ragas_eval_example.py and README.md.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
