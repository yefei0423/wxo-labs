# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
try:

    from ibm_watsonx_orchestrate.run.context import AgentRun
except ImportError:
    AgentRun = object  # Fallback for cloud execution sandbox

from ibm_watsonx_orchestrate.agent_builder.tools import tool

@tool
def read_user_email(context: AgentRun) -> str:
    """Read the user's email from the default context variable wxo_email_id."""
    req_context = context.request_context
    email = req_context.get("wxo_email_id", "EMAIL_NOT_FOUND")
    return f"The user's email from context is: {email}"
