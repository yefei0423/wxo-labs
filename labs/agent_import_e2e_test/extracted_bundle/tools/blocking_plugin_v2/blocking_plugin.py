"""
Input Blocking Pre-Invoke Plugin for Watsonx Orchestrate

This plugin blocks user input while long-running tools are executing.
It checks a state file to determine if a tool is currently running,
and if so, returns a "processing in progress" message to the user.

Author: Markus van Kempen | mvk@ca.ibm.com  
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
No bug too small, no syntax too weird.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.agent_builder.tools.types import (
    PythonToolKind,
    PluginContext,
    AgentPreInvokePayload,
    AgentPreInvokeResult,
)

# State file configuration
STATE_FILE = "/tmp/wxo_tool_state.json"
STATE_TIMEOUT_SECONDS = 300  # 5 minutes - auto-clear stale state


def read_state_file():
    """Read the current tool execution state from file."""
    if not os.path.exists(STATE_FILE):
        return {"is_running": False}
    
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            
            # Check if state is stale (timeout)
            if state.get("is_running") and state.get("started_at"):
                started_at = datetime.fromisoformat(state["started_at"])
                elapsed = (datetime.now() - started_at).total_seconds()
                
                if elapsed > STATE_TIMEOUT_SECONDS:
                    # State is stale - clear it
                    return {"is_running": False, "stale": True}
            
            return state
    except Exception as e:
        # If we can't read state, assume not running
        return {"is_running": False, "error": str(e)}


def get_user_context(plugin_context):
    """Extract user email and session ID from plugin context."""
    try:
        user_email = plugin_context.state["context"].get("wxo_email_id", "unknown")
        session_id = plugin_context.state["context"].get("session_id", "unknown")
        return user_email, session_id
    except Exception:
        return "unknown", "unknown"


@tool(
    description="Pre-invoke plugin that blocks user input while long-running tools execute",
    kind=PythonToolKind.AGENTPREINVOKE,
)
def blocking_plugin_v2(
    plugin_context: PluginContext,
    agent_pre_invoke_payload: AgentPreInvokePayload,
) -> AgentPreInvokeResult:
    """
    Pre-invoke plugin entry point.
    
    Checks if a long-running tool is currently executing.
    If yes, blocks the user from sending new messages.
    If no, allows normal agent processing.
    """
    
    # Get user context
    user_email, session_id = get_user_context(plugin_context)
    
    # Read current tool state
    state = read_state_file()
    
    # Check if a tool is currently running
    if state.get("is_running"):
        # BLOCK the user - tool is running
        result = AgentPreInvokeResult()
        result.continue_processing = False  # ← This blocks the agent!
        
        # Get tool details
        tool_name = state.get("tool_name", "unknown tool")
        progress = state.get("progress", 0)
        started_at = state.get("started_at", "unknown")
        
        # Calculate elapsed time
        try:
            start_time = datetime.fromisoformat(started_at)
            elapsed = int((datetime.now() - start_time).total_seconds())
            elapsed_str = f"{elapsed} seconds"
        except Exception:
            elapsed_str = "unknown"
        
        # Create blocking message
        modified_payload = agent_pre_invoke_payload.copy(deep=True)
        modified_payload.messages[-1].content.text = (
            f"⏳ **Processing in Progress**\n\n"
            f"A long-running operation is currently executing:\n\n"
            f"- **Tool:** `{tool_name}`\n"
            f"- **Progress:** {progress}%\n"
            f"- **Elapsed Time:** {elapsed_str}\n\n"
            f"Please wait for the operation to complete before sending new messages.\n"
            f"The agent will notify you when processing is finished.\n\n"
            f"_Your message has been blocked to prevent interference with the running operation._"
        )
        
        result.modified_payload = modified_payload
        return result
    
    # Check if state was stale and cleared
    if state.get("stale"):
        # Add a note to the message that state was auto-cleared
        result = AgentPreInvokeResult()
        result.continue_processing = True
        
        modified_payload = agent_pre_invoke_payload.copy(deep=True)
        original_text = modified_payload.messages[-1].content.text
        modified_payload.messages[-1].content.text = (
            f"{original_text}\n\n"
            f"[SYSTEM NOTE: Previous tool state was auto-cleared due to timeout.]"
        )
        
        result.modified_payload = modified_payload
        return result
    
    # No tool running - allow normal processing
    result = AgentPreInvokeResult()
    result.continue_processing = True
    result.modified_payload = agent_pre_invoke_payload
    return result

# Made by Research | 7 1/2 Floor
