# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---
"""
Python tool that reads WxO context variables directly from AgentRun.request_context.

This is Pattern C — direct Python tool context read.

When the askHR_agent calls this tool, WxO populates the five declared
context_variables (clientID, name, role, user_name, email_id) into the
AgentRun.request_context dict before the tool executes. No LLM mediation is
needed — the tool reads them directly from the execution context.

This complements the OpenAPI tool (Pattern A, LLM-mediated argument injection):
  - Pattern A: LLM reads context from instructions, passes as tool args → MCP server
  - Pattern C: Python tool reads request_context directly, no LLM involvement

Deploy:
  orchestrate tools import --file tools/hr_context_python_tool.py --kind python

Usage in agent:
  Add "read_hr_context" to the agent's tools list in askhr_agent.yaml.
"""

try:
    from ibm_watsonx_orchestrate.run.context import AgentRun
except ImportError:
    # Fallback for cloud sandbox execution environment.
    # The real AgentRun is available at runtime; this prevents an ImportError
    # during local development or when the module is not installed.
    AgentRun = object  # type: ignore[assignment, misc]

from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def read_hr_context(context: AgentRun) -> str:
    """Read all WxO HR context variables and system variables from the agent run context.

    Returns a formatted report of:
      - Custom HR context variables (clientID, name, role, user_name, email_id)
        injected via JWT token or /runs API payload.
      - WxO system variables (wxo_email_id, wxo_user_name, wxo_tenant_id,
        wxo_thread_id, wxo_run_id) automatically provided by the platform.

    All values are injected by WatsonX Orchestrate before this tool runs —
    do not ask the user for them.

    Args:
        context (AgentRun): The agent run context object injected by WxO.

    Returns:
        str: Formatted HR context report confirming which variables were injected.
    """
    req = context.request_context if hasattr(context, "request_context") else {}

    # ── Custom HR context variables (declared in context_variables list) ───────
    client_id  = req.get("clientID",  "NOT_INJECTED")
    name       = req.get("name",      "NOT_INJECTED")
    role       = req.get("role",      "NOT_INJECTED")
    user_name  = req.get("user_name", "NOT_INJECTED")
    email_id   = req.get("email_id",  "NOT_INJECTED")

    custom_vars = {
        "clientID": client_id, "name": name, "role": role,
        "user_name": user_name, "email_id": email_id,
    }
    all_custom_present = all(v != "NOT_INJECTED" for v in custom_vars.values())
    missing_custom = [k for k, v in custom_vars.items() if v == "NOT_INJECTED"]

    # ── WxO system variables (automatically injected by the platform) ──────────
    wxo_email_id   = req.get("wxo_email_id",   "NOT_AVAILABLE")
    wxo_user_name  = req.get("wxo_user_name",  "NOT_AVAILABLE")
    wxo_tenant_id  = req.get("wxo_tenant_id",  "NOT_AVAILABLE")
    wxo_thread_id  = req.get("wxo_thread_id",  "NOT_AVAILABLE")
    wxo_run_id     = req.get("wxo_run_id",      "NOT_AVAILABLE")

    system_vars = {
        "wxo_email_id":  wxo_email_id,
        "wxo_user_name": wxo_user_name,
        "wxo_tenant_id": wxo_tenant_id,
        "wxo_thread_id": wxo_thread_id,
        "wxo_run_id":    wxo_run_id,
    }
    system_injected = sum(1 for v in system_vars.values() if v != "NOT_AVAILABLE")

    custom_status = "✅ ALL PRESENT" if all_custom_present else f"⚠️ MISSING: {', '.join(missing_custom)}"
    system_status = f"✅ {system_injected}/5 injected" if system_injected > 0 else "⚠️ NONE (only available in web chat / authenticated sessions)"

    lines = [
        "═" * 56,
        "  HR Context — Pattern C (direct request_context read)",
        "═" * 56,
        "",
        "  ── Custom HR Context Variables ────────────────────",
        f"  Status    : {custom_status}",
        f"  clientID  : {client_id}",
        f"  name      : {name}",
        f"  role      : {role}",
        f"  user_name : {user_name}",
        f"  email_id  : {email_id}",
        "",
        "  ── WxO System Variables (auto-injected) ────────────",
        f"  Status         : {system_status}",
        f"  wxo_email_id   : {wxo_email_id}",
        f"  wxo_user_name  : {wxo_user_name}",
        f"  wxo_tenant_id  : {wxo_tenant_id}",
        f"  wxo_thread_id  : {wxo_thread_id}",
        f"  wxo_run_id     : {wxo_run_id}",
        "",
    ]

    if all_custom_present:
        lines.append(f"  HR Summary: {name} ({email_id}) | role={role} | client={client_id}")
    else:
        lines.append("  Action: Pass context via JWT claim or /runs API payload.")

    lines.append("═" * 56)
    return "\n".join(lines)
