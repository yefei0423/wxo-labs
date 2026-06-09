#!/usr/bin/env python3
"""Print trace_id from one chat/completions turn (stdout only; for shell scripts).

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.
"""
from __future__ import annotations

import argparse

from wxo_helpers import (
    chat_completions,
    get_agent_id_by_name,
    normalize_trace_id_for_api,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Output trace_id for orchestrate observability traces export.")
    p.add_argument("--agent-name", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument(
        "--thread-id-out",
        metavar="FILE",
        help="If set, write thread_id to this file (for debugging).",
    )
    args = p.parse_args()
    agent_id = get_agent_id_by_name(args.agent_name)
    body, hdr = chat_completions(agent_id, args.prompt)
    tid = normalize_trace_id_for_api(hdr.get("trace_id_header") or body.get("trace_id"))
    if not tid:
        raise SystemExit("No trace_id on response")
    print(tid)
    if args.thread_id_out:
        with open(args.thread_id_out, "w", encoding="utf-8") as f:
            f.write((body.get("thread_id") or "") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
