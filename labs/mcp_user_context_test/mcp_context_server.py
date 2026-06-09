# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server.stdio import stdio_server

# Initialize the MCP Server
# The server name and version are used during the 'initialize' handshake with Orchestrate.
app = Server("context-demo-server")

@app.list_tools()
async def list_tools() -> List[types.Tool]:
    """
    Lists available tools to the MCP client (Orchestrate).
    
    This method defines the schema for 'get_user_context'. 
    Note the 'injected_user_id' property; in a real WXO scenario, this 
    would be a hidden parameter mapped to {{user.id}}.
    """
    """List available tools."""
    return [
        types.Tool(
            name="get_user_context",
            description="Returns information about the user context received from the client.",
            inputSchema={
                "type": "object",
                "properties": {
                    "injected_user_id": {
                        "type": "string", 
                        "description": "User ID injected by Orchestrate via tool parameter."
                    },
                    "action_name": {
                        "type": "string",
                        "description": "A dummy action to perform."
                    }
                },
                "required": ["action_name"]
            },
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
    """
    Handles tool execution requests from the MCP client.
    
    Args:
        name: The name of the tool to execute.
        arguments: A dictionary of input parameters provided by the client.
        
    Returns:
        A list of TextContent objects containing the tool's response.
        
    Context Handling Logic:
    1. Pattern 1: Checks for a simulated 'WXO_USER_TOKEN' environment variable.
       In a production SSE deployment, this would be extracted from the 
       Authorization header of the HTTP request.
    2. Pattern 2: Checks for 'injected_user_id' within the JSON-RPC arguments.
       This relies on WXO's parameter injection mechanism.
    """
    if name == "get_user_context":
        action = arguments.get("action_name")
        print(f"[SERVER] ── tool={name!r}  action={action!r}", file=sys.stderr)
        print(f"[SERVER]    full arguments received: {arguments}", file=sys.stderr)

        # 1. Check for context passed in arguments (Pattern 2)
        injected_user = arguments.get("injected_user_id", "NOT_INJECTED")
        print(f"[SERVER]    Pattern 2 (arg injection) injected_user_id={injected_user!r}", file=sys.stderr)

        # 2. In a real SSE server (Pattern 1), you would access headers via the request context.
        # Since this is a stdio demonstration, we simulate checking for an environment variable
        # that could be set by the bridge if Orchestrate passed it.
        env_token = os.getenv("WXO_USER_TOKEN", "TOKEN_NOT_FOUND")
        print(f"[SERVER]    Pattern 1 (env/header token): {env_token[:25]}...", file=sys.stderr)
        
        response_text = (
            f"🛠️ Tool '{name}' executed for action: '{action}'\n\n"
            f"👤 Context Mapping Pattern Results:\n"
            f"- Pattern 1 (Header/Env Token): {env_token[:10]}... (SIMULATED)\n"
            f"- Pattern 2 (Injected Argument): {injected_user}\n"
        )
        
        if injected_user != "NOT_INJECTED":
            response_text += f"\n✅ Orchestrate Successfully passed the User ID via parameter injection."
            print(f"[SERVER]    → Pattern 2 SUCCESS  user={injected_user!r}", file=sys.stderr)
        else:
            response_text += f"\n⚠️ No user identity was found in the tool arguments."
            print(f"[SERVER]    → Pattern 2 NOT PRESENT (no injected_user_id argument)", file=sys.stderr)

        print(f"[SERVER]    Building and returning response...", file=sys.stderr)
        return [types.TextContent(type="text", text=response_text)]
    
    print(f"[SERVER] ERROR: unknown tool={name!r}", file=sys.stderr)
    raise ValueError(f"Unknown tool: {name}")

async def main():
    print("━" * 48, file=sys.stderr)
    print("[SERVER] 🚀  MCP Context Server starting (STDIO mode)", file=sys.stderr)
    print("[SERVER]    Tool  : get_user_context", file=sys.stderr)
    print("[SERVER]    Pattern 1 : reads WXO_USER_TOKEN env var", file=sys.stderr)
    print("[SERVER]    Pattern 2 : reads injected_user_id argument", file=sys.stderr)
    print("━" * 48, file=sys.stderr)
    # Run the server using stdin/stdout
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
