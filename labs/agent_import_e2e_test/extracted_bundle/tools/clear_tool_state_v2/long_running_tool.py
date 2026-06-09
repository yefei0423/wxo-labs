"""
Long-Running Tool for Testing Input Blocking

This tool simulates a long-running operation (default 30 seconds)
and updates a state file with progress information. The blocking
plugin reads this state to determine if user input should be blocked.

Author: Markus van Kempen | mvk@ca.ibm.com  
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
No bug too small, no syntax too weird.
"""

import json
import os
import time
from datetime import datetime

from ibm_watsonx_orchestrate.agent_builder.tools import tool

# State file configuration (must match blocking_plugin.py)
STATE_FILE = "/tmp/wxo_tool_state.json"


def write_state_file(state_data):
    """Write tool execution state to file."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=2)
    except Exception as e:
        print(f"Error writing state file: {e}")


def update_progress(progress):
    """Update just the progress field in the state file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            state["progress"] = progress
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error updating progress: {e}")


@tool(description="Simulates a long-running data processing operation")
def long_running_tool_v2(duration: int = 30) -> str:
    """
    Simulates a long-running operation that takes 'duration' seconds.
    
    Args:
        duration: Number of seconds to run (default: 30)
    
    Returns:
        Success message with processing statistics
    """
    
    # Validate duration
    if duration < 1:
        return "❌ Error: Duration must be at least 1 second"
    if duration > 300:
        return "❌ Error: Duration cannot exceed 300 seconds (5 minutes)"
    
    # Initialize state file - tool is now running
    initial_state = {
        "is_running": True,
        "tool_name": "long_running_tool",
        "started_at": datetime.now().isoformat(),
        "progress": 0,
        "duration": duration
    }
    write_state_file(initial_state)
    
    try:
        # Simulate long-running work with progress updates
        records_processed = 0
        
        for i in range(duration):
            # Simulate processing work
            time.sleep(1)
            records_processed += 50  # Simulate processing 50 records per second
            
            # Update progress
            progress = int(((i + 1) / duration) * 100)
            update_progress(progress)
            
            # Log progress every 5 seconds
            if (i + 1) % 5 == 0 or (i + 1) == duration:
                print(f"Progress: {progress}% ({i + 1}/{duration} seconds)")
        
        # Success!
        result = (
            f"✅ **Processing Complete!**\n\n"
            f"- **Duration:** {duration} seconds\n"
            f"- **Records Processed:** {records_processed:,}\n"
            f"- **Average Rate:** {records_processed // duration} records/second\n\n"
            f"The operation completed successfully. You can now send new messages."
        )
        
        return result
        
    except Exception as e:
        # Error occurred
        return f"❌ **Processing Failed**\n\nError: {str(e)}"
        
    finally:
        # Always clear the state file when done (success or failure)
        final_state = {
            "is_running": False,
            "tool_name": "long_running_tool",
            "completed_at": datetime.now().isoformat(),
            "progress": 100
        }
        write_state_file(final_state)
        print("Tool execution complete - state cleared")


@tool(description="Check the current status of any running tools")
def check_tool_status_v2() -> str:
    """
    Check if any tools are currently running and return their status.
    
    Returns:
        Status message with tool information
    """
    
    if not os.path.exists(STATE_FILE):
        return "ℹ️ No tools are currently running."
    
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        
        if not state.get("is_running"):
            return "ℹ️ No tools are currently running."
        
        # Tool is running - return status
        tool_name = state.get("tool_name", "unknown")
        progress = state.get("progress", 0)
        started_at = state.get("started_at", "unknown")
        
        # Calculate elapsed time
        try:
            start_time = datetime.fromisoformat(started_at)
            elapsed = int((datetime.now() - start_time).total_seconds())
            elapsed_str = f"{elapsed} seconds"
        except Exception:
            elapsed_str = "unknown"
        
        return (
            f"⏳ **Tool Currently Running**\n\n"
            f"- **Tool:** `{tool_name}`\n"
            f"- **Progress:** {progress}%\n"
            f"- **Elapsed Time:** {elapsed_str}\n\n"
            f"The tool is still processing. Please wait for completion."
        )
        
    except Exception as e:
        return f"❌ Error checking tool status: {str(e)}"


@tool(description="Manually clear the tool state (use if tool crashed)")
def clear_tool_state_v2() -> str:
    """
    Manually clear the tool state file.
    Use this if a tool crashed and left the state file in a bad state.
    
    Returns:
        Confirmation message
    """
    
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            return "✅ Tool state cleared successfully."
        else:
            return "ℹ️ No state file found - nothing to clear."
    except Exception as e:
        return f"❌ Error clearing state: {str(e)}"

# Made by Research | 7 1/2 Floor
