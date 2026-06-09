#!/usr/bin/env python3
"""
Minimal Ragas wiring once you have (question, answer, contexts, ground_truth).

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

`contexts` should be retrieved passages. **`ground_truth`** must be phrased so its
claims are **supportable from those contexts**, or context_precision / context_recall
from a strict judge can be ~0 even when the run succeeded.

Ragas APIs differ across versions; this script targets the classic `evaluate` entrypoint.
Adjust imports if you use Ragas 0.3+ collections metrics.

Requires: pip install -r requirements.txt and judge credentials — **OpenAI**
(`OPENAI_API_KEY`) or **watsonx** (`watsonx_url` or `WATSONX_URL`, `watsonx_api_key` or `WATSONX_APIKEY`,
`watsonx_project_id` or `WATSONX_PROJECT_ID`; optional `pip install -r requirements-ragas-watsonx.txt`).
Scripts load **`test_tools/.env`** when `python-dotenv` is installed (does not override existing exports). Use `--ragas-backend`.
"""

from __future__ import annotations

import argparse
import sys

from ragas_eval_backends import (
    build_evaluate_kwargs,
    detect_ragas_backend,
    load_repo_dotenv,
)


def main() -> int:
    load_repo_dotenv()
    p = argparse.ArgumentParser(description="Minimal Ragas context_precision / context_recall example.")
    p.add_argument(
        "--ragas-backend",
        choices=("auto", "openai", "watsonx"),
        default="auto",
        help="Judge backend: auto prefers watsonx env if set, else OpenAI.",
    )
    args = p.parse_args()

    try:
        from datasets import Dataset
        from ragas import evaluate
        # Legacy LLM-injection metrics (evaluate llm=...); avoid ragas.metrics import DeprecationWarning.
        from ragas.metrics._context_precision import context_precision
        from ragas.metrics._context_recall import context_recall
    except ImportError:
        print(
            "Install deps: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    backend = detect_ragas_backend(args.ragas_backend)
    if backend is None:
        print(
            "No judge credentials: set watsonx_url (or WATSONX_URL), watsonx_api_key "
            "(or WATSONX_APIKEY), watsonx_project_id (or WATSONX_PROJECT_ID) for watsonx, "
            "or OPENAI_API_KEY for OpenAI. watsonx: pip install -r requirements-ragas-watsonx.txt",
            file=sys.stderr,
        )
        return 1

    # Tightly aligned row so LLM-as-judge metrics are not trivially zero: ground_truth
    # statements should be entailed by contexts; answer should match the same facts.
    data = {
        "question": [
            "What is the capital of France, and what is its role?",
        ],
        "answer": [
            "Paris is the capital of France; it is also the largest city in the country.",
        ],
        "contexts": [
            [
                "Paris is the capital and largest city of France, with a population of about 2 million in the city proper.",
            ],
        ],
        "ground_truth": [
            "The capital of France is Paris. Paris is the largest city in France.",
        ],
    }
    dataset = Dataset.from_dict(data)
    result = evaluate(
        dataset,
        metrics=[context_precision, context_recall],
        **build_evaluate_kwargs(backend),
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
