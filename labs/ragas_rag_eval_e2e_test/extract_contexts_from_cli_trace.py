#!/usr/bin/env python3
"""Print Ragas-style contexts extracted from `orchestrate observability traces export` JSON.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.
"""
from __future__ import annotations

import argparse
import json
import sys

from wxo_helpers import tool_contexts_from_trace_export_file


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("trace_json", help="Path from traces export -o")
    p.add_argument("--split-passages", action="store_true")
    args = p.parse_args()
    try:
        ctx = tool_contexts_from_trace_export_file(args.trace_json, split_passages=args.split_passages)
    except (OSError, json.JSONDecodeError) as e:
        print(e, file=sys.stderr)
        return 1
    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
