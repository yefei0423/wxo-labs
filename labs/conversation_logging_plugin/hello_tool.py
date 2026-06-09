"""
Simple Hello Tool for testing.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
*No bug too small, no syntax too weird.*
"""

from ibm_watsonx_orchestrate.agent_builder.tools import tool

@tool(
    description="Say hello to the user",
)
def say_hello(name: str) -> str:
    """Say hello to the user"""
    return f"Hello, {name}! I am working correctly."
