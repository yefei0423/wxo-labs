# Author: Markus van Kempen | mvk@ca.ibm.com
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
# No bug too small, no syntax too weird.
try:

    from ibm_watsonx_orchestrate.run.context import AgentRun
except ImportError:
    # Fallback for cloud execution environment
    class AgentRun:
        def __init__(self):
            self.request_context = {}

from typing import Optional
from pydantic import BaseModel, Field
from ibm_watsonx_orchestrate.agent_builder.tools import tool

class FinancialImpactInput(BaseModel):
    """
    Schema for financial impact selection.
    """
    # Setting an 'initial value' using Field(default=...)
    inferred_financial_amount: int = Field(
        default=1000, 
        description="The initial financial amount. Defaults to 1000."
    )
    potential_gross_financial_impact: Optional[int] = Field(
        default=None,
        description="The actual gross financial impact to be recorded."
    )

@tool
def financial_impact_selection(context: AgentRun, input_data: FinancialImpactInput) -> str:
    """
    Demonstrates setting an initial value for a number input field.
    """
    # 1. Fetch from 'flow' context if available (Dynamic Initial Value)
    req_context = context.request_context
    flow_value = req_context.get("flow_inferred_amount")
    
    # 2. If flow_value exists, it acts as the initial value over the Pydantic default
    initial_value = flow_value if flow_value is not None else input_data.inferred_financial_amount
    
    return f"Initial Value determined: {initial_value}. Using context: {req_context}"

@tool
def calculate_net_impact(input_data: FinancialImpactInput) -> str:
    """
    Calculates net financial impact.
    """
    return f"Calculated Net Impact using base value {input_data.inferred_financial_amount}"
