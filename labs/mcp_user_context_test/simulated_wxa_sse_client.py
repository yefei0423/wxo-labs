# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---
"""
This script simulates Watsonx Orchestrate connecting to our MCP SSE Server
and explicitly passing a simulated User Bearer Token in the headers as it would
during an OAuth2 connection flow.

Dependencies:
pip install mcp
"""

import asyncio
import os
from mcp.client.sse import sse_client
from mcp import ClientSession

SEP = "─" * 56

async def run_sse_test():
    print(f"\n{'\u2501'*56}")
    print("🧪  Simulated WxO SSE Client — Flow Trace")
    print(f"{'\u2501'*56}\n")

    # ── Step 1: Build the simulated Bearer token ─────────────────────────
    simulated_wxo_bearer_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.wxo_simulated_user_payload"
    print(f"[1/4] 🔑 Simulated Bearer token built")
    print(f"      Token : {simulated_wxo_bearer_token[:60]}")

    # ── Step 2: Build request headers (exactly as WxO does) ─────────────
    headers = {
        "Authorization": f"Bearer {simulated_wxo_bearer_token}",
        "X-Wxo-Agent-Id": "agent-12345",   # WxO passes tracing headers too
    }
    print(f"\n[2/4] 📤 HTTP headers that will be sent to /sse:")
    for k, v in headers.items():
        print(f"      {k}: {v[:70]}")

    # ── Step 3: Open connection + MCP handshake ──────────────────────
    print(f"\n[3/4] 🌐 Opening SSE connection → http://localhost:8000/sse")

    try:
        # 3. Connect via SSE, explicitly passing the Authorization Headers
        # The signature includes headers directly: sse_client(url: str, headers: dict | None = None, ...)
        async with sse_client("http://localhost:8000/sse", headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("      ✅ MCP handshake complete")

                # ── Step 4: Call the tool ─────────────────────────────────
                print(f"\n[4/4] 🛠️  Calling tool: get_session_identity")
                print(f"      Arguments: {{\"action\": \"Check Auth Headers\"}}")

                result = await session.call_tool("get_session_identity", {"action": "Check Auth Headers"})

                print(f"\n{SEP}")
                print("📩  MCP Server Response:")
                print(SEP)
                print(result.content[0].text)
                print(f"{SEP}\n")

    except Exception as e:
        print(f"\n❌ Connection failed. Is mcp_sse_server.py running on port 8000?")
        print(f"   Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_sse_test())
