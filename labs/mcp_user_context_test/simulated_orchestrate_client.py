# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---

import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SEP = "─" * 56

async def run_test():
    """
    Simulates a Watsonx Orchestrate session calling an MCP server.
    
    This simulation covers two critical scenarios:
    1. Direct tool call without specific user identity mapping.
    2. Context-aware call where WXO has 'injected' the user's ID into the payload.
    """
    print(f"\n{'\u2501'*56}")
    print("🧪  Simulated WxO STDIO Client — Flow Trace")
    print(f"{'\u2501'*56}\n")

    # ── Step 1: Prepare server launch parameters ───────────────────────
    token_sim = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_wxo_user_token"
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_context_server.py"],
        env={**os.environ, "WXO_USER_TOKEN": token_sim}
    )
    print(f"[1/5] ⚙️  Server launch params:")
    print(f"      command : python mcp_context_server.py")
    print(f"      env     : WXO_USER_TOKEN={token_sim[:40]}...")

    # ── Step 2: Connect via STDIO ──────────────────────────────────
    print(f"\n[2/5] 🚀 Spawning MCP server process via STDIO...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"      ✅ MCP handshake complete")

            # ── Step 3: List available tools ────────────────────────────
            tools = await session.list_tools()
            print(f"\n[3/5] 🗂️  Tools available on server:")
            for t in tools.tools:
                print(f"      • {t.name}: {t.description[:65]}")

            # ── Step 4: Scenario A — no context injection ─────────────────
            args_a = {"action_name": "Check Status"}
            print(f"\n[4/5] {SEP}")
            print(f"      Scenario A — call WITHOUT context injection")
            print(f"      Arguments sent: {args_a}")
            print(SEP)
            result_a = await session.call_tool("get_user_context", args_a)
            print(result_a.content[0].text)

            # ── Step 5: Scenario B — with context injection (Pattern 2) ─────
            args_b = {"action_name": "Update Maximo", "injected_user_id": "mvk@ca.ibm.com"}
            print(f"\n[5/5] {SEP}")
            print(f"      Scenario B — call WITH context injection (Pattern 2)")
            print(f"      Arguments sent: {args_b}")
            print(SEP)
            result_b = await session.call_tool("get_user_context", args_b)
            print(result_b.content[0].text)

    print(f"\n{'\u2501'*56}")
    print("✅  Test complete")
    print(f"{'\u2501'*56}\n")

if __name__ == "__main__":
    # Ensure we are in the right directory to find the server script
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(run_test())
