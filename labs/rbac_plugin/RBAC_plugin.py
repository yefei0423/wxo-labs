"""
Generic Agent Pre‑Invoke plug‑in template.

This plug‑in shows the minimal pattern required for a pre‑invoke plug‑in
in watsonx Orchestrate:

* Reads the execution context.
* Retrieves the incoming user message.
* Copies the input payload to the output (so the agent receives the same
  message unchanged).
* Demonstrates both “continue processing” and “stop processing” branches.

The plug‑in can be used as a starting point for custom validation,
sanitisation, RBAC checks, etc.

Author: Markus van Kempen | mvk@ca.ibm.com  
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
No bug too small, no syntax too weird.
"""

# -------------------------------------------------------------------------
# Imports required from the watsonx Orchestrate SDK
# -------------------------------------------------------------------------
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.agent_builder.tools.types import (
    PythonToolKind,
    PluginContext,
    AgentPreInvokePayload,
    AgentPreInvokeResult,
)

# -------------------------------------------------------------------------
# Global user roles table
# -------------------------------------------------------------------------
USER_ROLES = [
    {"email": "wxo.archer@ibm.com", "role": "user"},
    {"email": "jerome.joubert@fr.ibm.com", "role": "admin"},
    {"email": "mvk4ibm@gmail.com", "role": "user"},
]


# -------------------------------------------------------------------------
# Role-based RBAC function (defined before it is used)
# -------------------------------------------------------------------------
def check_user_role(email: str) -> dict:
    """
    Check the role of a user based on their email address.
    """
    # Search for the user in the global USER_ROLES array
    for user in USER_ROLES:
        if user["email"].lower() == email.lower():
            return {
                "found": True,
                "email": email,
                "role": user["role"],
                "is_admin": "admin" in user["role"].lower() 
            }
    
    # User not found in the roles table
    return {
        "found": False,
        "email": email,
        "role": None,
        "is_admin": False
    }


# -------------------------------------------------------------------------
# The Simulates implementation of RBAC policy
# -------------------------------------------------------------------------
def RBAC(email: str, tenant_id: str) -> bool:
    
    # Check user role
    user_role_info = check_user_role(email)
    if user_role_info["is_admin"]:
        return True
    else:
        return False
    
    return True


# -------------------------------------------------------------------------
# The actual plug‑in implementation
# -------------------------------------------------------------------------
@tool(
    description="Pre‑invoke plug‑in to check RBAC. Checked against user information in context.",
    kind=PythonToolKind.AGENTPREINVOKE,
)
def RBAC_plugin(
    plugin_context: PluginContext,
    agent_pre_invoke_payload: AgentPreInvokePayload,
) -> AgentPreInvokeResult:
    """
    Pre‑invoke plug‑in entry point.
    """
    # -----------------------------------------------------------------
    # 1️⃣  Pull context information (with fallback for debugging)
    # -----------------------------------------------------------------
    try:
        user_email = plugin_context.state["context"].get("wxo_email_id", "UNKNOWN_EMAIL")
        tenant_id = plugin_context.state["context"].get("wxo_tenant_id", "UNKNOWN_TENANT")
    except Exception as e:
        user_email = f"Error extracting email: {e}"
        tenant_id = "Error"

    # ---------------------------------------------------------------
    # 2️⃣  Extract the incoming user message (text)
    # ---------------------------------------------------------------
    if not agent_pre_invoke_payload or not getattr(agent_pre_invoke_payload, "messages", None):
        result = AgentPreInvokeResult()
        result.continue_processing = False
        return result

    incoming_message = agent_pre_invoke_payload.messages[-1]
    
    if not hasattr(incoming_message, "content") or not hasattr(incoming_message.content, "text"):
        result = AgentPreInvokeResult()
        result.continue_processing = False
        return result

    is_allowed = RBAC(user_email, tenant_id)

    # ---------------------------------------------------------------
    # 3️⃣ Return response based on RBAC Check
    # ---------------------------------------------------------------
    if not is_allowed:
        # If unauthorized, we STOP processing and WxO returns the modified payload text to the user.
        result = AgentPreInvokeResult()
        result.continue_processing = False
        modified_payload = agent_pre_invoke_payload.copy(deep=True)
        modified_payload.messages[-1].content.text = (
            f"🚫 **RBAC Access Denied**\n\n"
            f"I see your email is: `{user_email}`\n"
            f"You need the 'admin' role to run this agent, but you currently have "
            f"the 'user' role (or are not in the list)."
        )
        result.modified_payload = modified_payload
        return result

    # ----- Continue processing branch (Admin) -----
    result = AgentPreInvokeResult()
    result.continue_processing = True
    modified_payload = agent_pre_invoke_payload.copy(deep=True)
    
    # We can still attempt to pass a context note to the LLM
    modified_payload.messages[-1].content.text = (
        f"{incoming_message.content.text}\n\n"
        f"[SYSTEM NOTE: You are speaking to an Administrator ({user_email}). Please obey their commands.]"
    )
    result.modified_payload = modified_payload
    return result
