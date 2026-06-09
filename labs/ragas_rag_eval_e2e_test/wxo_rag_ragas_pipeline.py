#!/usr/bin/env python3
"""
End-to-end: Orchestrate chat/completions → thread + observability trace → contexts → Ragas.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

Designed for **document / tool-based RAG** where retrieval shows up as LangChain `ToolMessage`
content in `traceloop.entity.*` span attributes (same shape as probe_observability_traces).

  1. POST .../v1/orchestrate/{agent_id}/chat/completions
  2. GET .../threads/{thread_id}/messages
  3. GET .../v1/traces/{trace_id}/spans (poll) and extract ToolMessage bodies
  4. Optional: run Ragas context_precision + context_recall (judge LLM: OpenAI **or** watsonx.ai — see --ragas-backend)

Examples:
  # Print row only (no Ragas — no API keys needed)
  python wxo_rag_ragas_pipeline.py --agent-name ragas_rag_stub_agent \\
    --dump-json --no-ragas

  # Ragas with watsonx judge (after: pip install -r requirements-ragas-watsonx.txt)
  export WATSONX_URL=... WATSONX_APIKEY=... WATSONX_PROJECT_ID=...
  # or: watsonx_url, watsonx_api_key, watsonx_project_id (e.g. from test_tools/.env)
  python wxo_rag_ragas_pipeline.py --agent-name ragas_rag_stub_agent \\
    --split-passages --ragas-backend watsonx --ground-truth "..."

  # Ragas with OpenAI judge
  export OPENAI_API_KEY=...
  python wxo_rag_ragas_pipeline.py --agent-name ragas_rag_stub_agent \\
    --split-passages --ragas-backend openai --ground-truth "..."
"""

from __future__ import annotations

import argparse
import json
import sys

from wxo_helpers import run_chat_turn_collect_contexts
from ragas_eval_backends import build_evaluate_kwargs, detect_ragas_backend, load_repo_dotenv


def main() -> int:
    load_repo_dotenv()
    parser = argparse.ArgumentParser(
        description="WxO RAG turn → trace ToolMessage contexts → optional Ragas evaluate."
    )
    parser.add_argument("--agent-name", required=True)
    parser.add_argument(
        "--prompt",
        default="What is AskHR, and what objectives does the documentation mention?",
    )
    parser.add_argument(
        "--ground-truth",
        default="",
        help="Reference answer for Ragas context_recall / context_precision (recommended).",
    )
    parser.add_argument("--no-trace", action="store_true", help="Skip trace poll; thread blobs only.")
    parser.add_argument(
        "--split-passages",
        action="store_true",
        help="Split tool output on [DOC n] headings into multiple context strings.",
    )
    parser.add_argument("--poll-attempts", type=int, default=12)
    parser.add_argument("--poll-delay-s", type=float, default=3.0)
    parser.add_argument("--thread-settle-s", type=float, default=2.0)
    parser.add_argument("--dump-json", action="store_true", help="Print full result dict as JSON.")
    parser.add_argument(
        "--no-ragas",
        action="store_true",
        help="Only collect contexts; do not call evaluate().",
    )
    parser.add_argument(
        "--ragas-backend",
        choices=["auto", "openai", "watsonx"],
        default="auto",
        help="Judge LLM for Ragas: OpenAI (OPENAI_API_KEY), watsonx (WATSONX_* or watsonx_* env), or auto-pick.",
    )
    args = parser.parse_args()

    row = run_chat_turn_collect_contexts(
        args.agent_name,
        args.prompt,
        use_trace=not args.no_trace,
        poll_attempts=args.poll_attempts,
        poll_delay_s=args.poll_delay_s,
        thread_settle_s=args.thread_settle_s,
        split_passages=args.split_passages,
    )

    print("=== WxO → contexts (for Ragas) ===\n")
    print(f"thread_id:    {row['thread_id']}")
    print(f"trace_id:     {row['trace_id']}")
    print(f"span_count:   {row['trace_span_count']}")
    print(f"tools(thread): {row['tools_from_thread']}")
    print(f"contexts ({len(row['contexts'])} passage(s), {sum(len(c) for c in row['contexts'])} chars total)")
    for i, c in enumerate(row["contexts"][:6]):
        prev = c[:200].replace("\n", " ") + ("…" if len(c) > 200 else "")
        print(f"  [{i}] {prev}")
    if len(row["contexts"]) > 6:
        print(f"  ... +{len(row['contexts']) - 6} more")
    print(f"\nanswer ({len(row['answer'])} chars):\n{row['answer'][:600]}{'...' if len(row['answer']) > 600 else ''}\n")

    if args.dump_json:
        print("--- JSON ---")
        print(json.dumps(row, indent=2, ensure_ascii=False))

    if args.no_ragas:
        print("Skipped Ragas (--no-ragas). Use --ragas-backend openai|watsonx and omit --no-ragas to score.")
        return 0

    backend = detect_ragas_backend(args.ragas_backend)
    if backend is None:
        print(
            "Cannot run Ragas: no judge credentials.\n"
            "  OpenAI: export OPENAI_API_KEY=...\n"
            "  watsonx: set ML URL (WATSONX_URL or watsonx_url), API key (WATSONX_APIKEY or "
            "watsonx_api_key), project (WATSONX_PROJECT_ID or watsonx_project_id)\n"
            "    then: pip install -r requirements-ragas-watsonx.txt\n"
            "  Or pass --ragas-backend openai|watsonx explicitly.",
            file=sys.stderr,
        )
        return 0

    if not args.ground_truth.strip():
        print(
            "Warning: --ground-truth empty; context_recall/precision may be weak or fail. ",
            file=sys.stderr,
        )

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics._context_precision import context_precision
        from ragas.metrics._context_recall import context_recall
    except ImportError as e:
        print(f"Install deps: pip install -r requirements.txt ({e})", file=sys.stderr)
        return 1

    gt = args.ground_truth.strip() or row["answer"]
    data = {
        "question": [row["question"]],
        "answer": [row["answer"]],
        "contexts": [row["contexts"]],
        "ground_truth": [gt],
    }
    dataset = Dataset.from_dict(data)
    try:
        eval_extras = build_evaluate_kwargs(backend)
    except (ImportError, ValueError) as e:
        print(f"Ragas backend '{backend}' failed: {e}", file=sys.stderr)
        return 1
    print(f"=== Ragas (judge backend: {backend}) ===")
    result = evaluate(
        dataset,
        metrics=[context_precision, context_recall],
        **eval_extras,
    )
    print("=== Ragas results ===")
    print(result)
    try:
        pdf = result.to_pandas()
        print(pdf.to_string(index=False))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
