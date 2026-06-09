#!/usr/bin/env python3
"""
One-shot probe: call chat/completions, then show where retrieval-related text might appear.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

Use this to discover how your agent surfaces KB chunks (thread messages vs traces).

Example:
  python probe_retrieval_sources.py --agent-name my_rag_agent --prompt "What is AskHR?"
  python probe_retrieval_sources.py --agent-name my_rag_agent --prompt "..." --dump-trace
"""

from __future__ import annotations

import argparse
import json
import sys

from wxo_helpers import (
    assistant_answer_from_chat_body,
    candidate_contexts_from_thread_messages,
    chat_completions,
    get_agent_id_by_name,
    get_thread_messages,
    poll_trace_spans,
    prompt_like_strings_from_spans,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe WxO for RAG retrieval text sources.")
    parser.add_argument("--agent-name", required=True, help="Orchestrate agent name (not UUID).")
    parser.add_argument("--prompt", default="Summarize what this agent can do.", help="User message.")
    parser.add_argument(
        "--dump-trace",
        action="store_true",
        help="Poll GET /v1/traces/{id}/spans and print prompt-like span attributes.",
    )
    parser.add_argument(
        "--raw-messages",
        action="store_true",
        help="Print full thread messages JSON (large).",
    )
    args = parser.parse_args()

    agent_id = get_agent_id_by_name(args.agent_name)
    body, hdr = chat_completions(agent_id, args.prompt)
    thread_id = body.get("thread_id")
    trace_body = body.get("trace_id")
    answer = assistant_answer_from_chat_body(body)

    print("=== chat/completions summary ===")
    print(f"thread_id (body): {thread_id}")
    print(f"trace_id (body):  {trace_body}")
    print(f"trace_id (header traceparent): {hdr.get('trace_id_header')}")
    print(f"answer preview: {answer[:400]!r}{'...' if len(answer) > 400 else ''}\n")

    if not thread_id:
        print("No thread_id on response; cannot fetch /threads/.../messages.", file=sys.stderr)
        return 1

    messages = get_thread_messages(thread_id)
    candidates = candidate_contexts_from_thread_messages(messages)
    print(f"=== candidate context strings from thread messages ({len(candidates)}) ===")
    for i, c in enumerate(candidates[:20]):
        preview = c[:500] + ("…" if len(c) > 500 else "")
        print(f"--- [{i}] ({len(c)} chars) ---\n{preview}\n")
    if len(candidates) > 20:
        print(f"... {len(candidates) - 20} more (truncated in listing)")

    if args.raw_messages:
        print("\n=== raw thread messages JSON ===")
        print(json.dumps(messages, indent=2, default=str))

    if args.dump_trace:
        tid = hdr.get("trace_id_header") or trace_body
        if not tid:
            print("No trace id from header or body; skipping trace poll.", file=sys.stderr)
            return 0
        print(f"\n=== polling trace spans for {tid} ===")
        spans_payload = poll_trace_spans(str(tid))
        if not spans_payload:
            print("No span payload returned.", file=sys.stderr)
            return 0
        prompts = prompt_like_strings_from_spans(spans_payload)
        print(f"prompt/context-like span strings: {len(prompts)}")
        for i, p in enumerate(prompts[:10]):
            prev = p[:800] + ("…" if len(p) > 800 else "")
            print(f"--- trace text [{i}] ({len(p)} chars) ---\n{prev}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
