"""
Stub knowledge-base text for Ragas E2E testing.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

Returns deterministic passages so `GET .../threads/.../messages` can surface
retrieval-like content in tool outputs (see probe_retrieval_sources.py).
"""
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def ragas_retrieve_stub(topic: str) -> str:
    """
    Retrieve internal HR assistant reference passages for the given topic or question.

    Use this tool whenever the user asks about AskHR, HR automation, leave policies,
    benefits, or watsonx Orchestrate HR use cases. Pass their question as `topic`.

    Args:
        topic: User question or keywords (e.g. "AskHR", "leave balance", "benefits").
    """
    # Fixed chunks — useful as synthetic "ground truth" for Ragas context metrics.
    return (
        "[DOC 1 — AskHR overview]\n"
        "AskHR is an AI assistant use case for employees: one conversational entry "
        "point for routine HR tasks such as checking leave balances, requesting time "
        "off, updating profile fields, and answering benefits questions.\n\n"
        "[DOC 2 — Objectives]\n"
        "Objectives: (1) Automate everyday HR tasks with approvals where needed; "
        "(2) Provide natural-language access instead of many portals; (3) Connect "
        "securely to HR systems via OpenAPI-style connectors; (4) Use watsonx "
        "Orchestrate for reasoning, routing, and reliable tool execution.\n\n"
        "[DOC 3 — Outcomes]\n"
        "Expected outcomes: faster employee support, less manual HR handling, and "
        "higher satisfaction while keeping access controlled by enterprise identity "
        "and policies."
    )
