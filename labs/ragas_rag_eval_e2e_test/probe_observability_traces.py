#!/usr/bin/env python3
"""
Probe whether OpenTelemetry traces help recover text usable as Ragas `contexts`.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

Flow:
  1) POST chat/completions
  2) GET thread messages → baseline tool/context blobs
  3) Poll GET /v1/traces/{trace_id}/spans
  4) Report span summary, interesting attributes, overlap vs thread blobs

Example:
  python probe_observability_traces.py --agent-name ragas_rag_stub_agent
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from wxo_helpers import (
    analyze_trace_for_rag,
    assistant_answer_from_chat_body,
    candidate_contexts_from_thread_messages,
    chat_completions,
    fetch_trace_spans_response,
    get_agent_id_by_name,
    get_thread_messages,
    normalize_trace_id_for_api,
    poll_trace_spans,
    thread_trace_overlap_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test WxO observability traces for RAG-style context recovery."
    )
    parser.add_argument("--agent-name", required=True, help="Orchestrate agent name.")
    parser.add_argument(
        "--prompt",
        default="What is AskHR, and what objectives does the documentation mention?",
        help="User message.",
    )
    parser.add_argument("--thread-settle-s", type=float, default=2.0)
    parser.add_argument("--poll-attempts", type=int, default=12)
    parser.add_argument("--poll-delay-s", type=float, default=3.0)
    parser.add_argument(
        "--dump-analysis-json",
        action="store_true",
        help="Print full analyze_trace_for_rag() dict as JSON.",
    )
    args = parser.parse_args()

    print("=== Observability trace probe (Ragas context recovery) ===\n")

    agent_id = get_agent_id_by_name(args.agent_name)
    body, hdr = chat_completions(agent_id, args.prompt)
    thread_id = body.get("thread_id")
    trace_body = body.get("trace_id")
    trace_hdr = hdr.get("trace_id_header")
    answer = assistant_answer_from_chat_body(body)

    tid = normalize_trace_id_for_api(trace_hdr) or normalize_trace_id_for_api(trace_body)

    print("--- chat/completions ---")
    print(f"thread_id: {thread_id}")
    print(f"trace_id (raw body): {trace_body!r}")
    print(f"trace_id (traceparent): {trace_hdr!r}")
    print(f"trace_id (normalized for GET): {tid!r}")
    print(f"answer ({len(answer)} chars): {answer[:320]!r}{'...' if len(answer) > 320 else ''}\n")

    if not thread_id:
        print("No thread_id; cannot compare thread contexts.", file=sys.stderr)
        return 1

    time.sleep(max(0.0, args.thread_settle_s))
    messages = get_thread_messages(thread_id)
    thread_contexts = candidate_contexts_from_thread_messages(messages)
    print(f"--- thread baseline: {len(thread_contexts)} context blob(s) from messages API ---")
    for i, c in enumerate(thread_contexts[:5]):
        print(f"  [{i}] ({len(c)} chars) {c[:200].replace(chr(10), ' ')}…")

    if not tid:
        print("\nNo trace id on response; cannot call /v1/traces/.../spans.", file=sys.stderr)
        print("Try another agent/model path or check if tracing is disabled for this route.")
        return 0

    status, first = fetch_trace_spans_response(tid)
    print(f"\n--- first GET /v1/traces/{{id}}/spans → HTTP {status} ---")
    if status != 200:
        print(
            "If this is 401/403, the CLI token may not allow observability reads; "
            "try an API key / role that can read traces.",
            file=sys.stderr,
        )

    print(f"Polling up to {args.poll_attempts}× (delay {args.poll_delay_s}s)…")
    spans = poll_trace_spans(tid, attempts=args.poll_attempts, delay_s=args.poll_delay_s)
    if not spans:
        print("\nVERDICT: No span payload after polling — traces did not help this run.")
        print(
            "Common causes: wrong trace_id format, delayed export, permissions, "
            "or traces not emitted for this request path."
        )
        return 0

    analysis = analyze_trace_for_rag(spans, min_string_len=80, max_records=50)
    overlap = thread_trace_overlap_report(thread_contexts, spans)

    print(f"\n--- trace shape ---")
    print(f"span_count (extracted): {analysis['span_count']}")
    print(f"span_names (sample): {analysis['span_names'][:12]}")
    print("top_attribute_keys (frequency):")
    for k, v in list(analysis["top_attribute_keys"].items())[:15]:
        print(f"  {k}: {v}")

    print(f"\n--- long 'interesting' attribute strings ({len(analysis['interesting_long_strings'])}) ---")
    for i, rec in enumerate(analysis["interesting_long_strings"][:8]):
        print(
            f"  [{i}] {rec['key']} | span={rec['span_name'][:40]!r} | "
            f"len={rec['length']}\n      {rec['preview'][:300]}…"
        )

    print("\n--- overlap: thread tool/context blobs vs trace text ---")
    print(json.dumps(overlap, indent=2))

    frac = float(overlap.get("fraction") or 0)
    if overlap.get("trace_available") and frac >= 0.5:
        print(
            "\nVERDICT: Traces likely HELP for Ragas — much of the thread-visible "
            "retrieval/tool text also appears in span attributes (often as part of prompts). "
            "You may still need splitting/heuristics; chunks are not guaranteed to be isolated."
        )
    elif overlap.get("trace_available") and analysis["interesting_long_strings"]:
        print(
            "\nVERDICT: Traces PARTIALLY help — there is rich span text, but it may not "
            "match thread blobs cleanly (merged prompts, different encoding). "
            "Inspect `interesting_long_strings` and decide if merged prompts are acceptable as `contexts`."
        )
    elif overlap.get("trace_available"):
        print(
            "\nVERDICT: Traces WEAK for this agent — spans exist but heuristic extraction "
            "found little usable long text. Try widening keys in wxo_helpers._is_interesting_rag_attr_key "
            "or dump raw spans in your observability UI."
        )
    else:
        print("\nVERDICT: Traces unavailable — rely on thread messages or instrumentation.")

    if args.dump_analysis_json:
        print("\n--- full analysis JSON ---")
        print(json.dumps(analysis, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
