# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---
"""
This script demonstrates an MCP Server exposed over Server-Sent Events (SSE).
It explicitly handles the 'Authorization' HTTP header passed by Watsonx Orchestrate (WxO)
when a user is logged into the platform and WxO invokes a tool on their behalf.

Dependencies:
pip install mcp starlette uvicorn
"""

import sys
import logging
import time
from contextvars import ContextVar
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
import uvicorn

import mcp.types as types
from mcp.server import Server
from mcp.server.sse import SseServerTransport

# Initialize State/Context
# We use ContextVar to safely store the WxO request token in a way that is 
# isolated per-request in the async environment so tools can read it later.
wxo_token_ctx: ContextVar[str] = ContextVar("wxo_token", default="NO_BEARER_TOKEN_FOUND")

app = Server("sse-wxo-context-demo")

# ── Structured debug logging ───────────────────────────────────────────────────
class _ColourFormatter(logging.Formatter):
    RESET = "\033[0m"; GREY = "\033[90m"; CYAN = "\033[96m"
    GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"
    COLOURS = {logging.DEBUG: "\033[90m", logging.INFO: "\033[96m",
               logging.WARNING: "\033[93m", logging.ERROR: "\033[91m"}
    def format(self, record):
        c = self.COLOURS.get(record.levelno, self.RESET)
        ts = self.formatTime(record, "%H:%M:%S")
        return f"{self.GREY}{ts}{self.RESET} {c}{record.levelname:<7}{self.RESET} {record.getMessage()}"

_h = logging.StreamHandler()
_h.setFormatter(_ColourFormatter())
log = logging.getLogger("wxo.mcp")
log.setLevel(logging.DEBUG)
log.addHandler(_h)
log.propagate = False

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Provide a tool specifically for validating the header extraction."""
    return [
        types.Tool(
            name="get_session_identity",
            description="Fetches the user's secure identity based on the WxO Authorization Token.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "What you want to do (e.g., 'simulate action')"
                    }
                },
                "required": []
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle Orchestrate tool invocations."""
    log.info(f"── MCP tool call  name={name!r}  args={arguments}")
    if name == "get_session_identity":
        # 3. Read the Token from the active Context Var that was set during SSE Handshake
        token = wxo_token_ctx.get()
        log.debug(f"   Context var token: {token[:30] if token != 'NO_BEARER_TOKEN_FOUND' else token}")
        
        response = (
            f"✅ SSE Tool Invoked via WxO!\n"
            f"🔍 The tool securely extracted the following Token from the HTTP Request Headers:\n\n"
            f"> Bearer {token}\n\n"
            f"💡 In production, you would exchange this token into an OBO (On-Behalf-Of) "
            f"flow to pass into backing enterprise systems like Maximo!"
        )
        log.info("   → Tool response built, returning to MCP client")
        return [types.TextContent(type="text", text=response)]
    log.error(f"   Unknown tool requested: {name!r}")
    raise ValueError(f"Unknown tool: {name}")

# Create the SSE Transport at a specific message endpoint
sse = SseServerTransport("/messages")

from starlette.responses import Response

async def handle_sse(request: Request):
    """
    1. Orchestrate connects to the SSE Event Stream. 
    Here we intercept the headers BEFORE the MCP initialization handshake.
    """
    client = request.client.host if request.client else "unknown"
    log.info(f"── SSE connect  client={client}")
    log.debug(f"   Incoming headers: { dict(request.headers) }")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        # 2. Extract Token and save to context for the tool to access contextually
        wxo_token_ctx.set(token)
        log.info(f"   ✅ Bearer token set  preview={token[:20]}...")
    else:
        wxo_token_ctx.set("NO_BEARER_TOKEN_FOUND")
        log.warning("   ⚠️  No Authorization header — token will be NO_BEARER_TOKEN_FOUND")

    log.debug("   Starting MCP SSE session...")
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as endpoints:
        await app.run(
            endpoints[0],
            endpoints[1],
            app.create_initialization_options()
        )
    log.info(f"   SSE session closed  client={client}")
    return Response()

import base64
import json as _json

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.responses import JSONResponse


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without signature verification (claims are not secret)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            log.warning(f"   JWT malformed: expected 3 segments, got {len(parts)}")
            return {}
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        claims = _json.loads(base64.b64decode(padded))
        log.debug(f"   JWT decoded OK  keys={list(claims.keys())}")
        return claims
    except Exception as exc:
        log.error(f"   JWT decode failed: {exc}")
        return {}


async def handle_check_identity(request: Request):
    """
    REST endpoint for WxO OpenAPI tool calls.
    WxO calls this via HTTP GET/POST and passes the user's Bearer token in the
    Authorization header. We extract it and return it as JSON — no SSE needed.
    """
    t0 = time.monotonic()
    client = request.client.host if request.client else "unknown"
    log.info(f"── REST  {request.method} /check-identity  client={client}")
    log.debug("   Request headers:")
    for k, v in request.headers.items():
        if k.lower() == "authorization":
            tok = v.split(" ", 1)[1] if " " in v else v
            display = f"Bearer {tok[:12]}...{tok[-6:]}" if len(tok) > 20 else v
            log.debug(f"     {k}: {display}")
        else:
            log.debug(f"     {k}: {v}")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        log.info(f"   ✅ Bearer token present  len={len(token)} chars")
        claims = _decode_jwt_payload(token)
        log.debug(f"   JWT identity claims: { {k: v for k, v in claims.items() if k in ('sub','email','preferred_username','iat','exp')} }")
        username = (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("sub")
            or "unknown"
        )
        log.info(f"   👤 username resolved → {username}")
        result = {
            "status": "success",
            "message": (
                "✅ WxO Identity Check: Token successfully extracted from HTTP headers!\n"
                "💡 In production, exchange this token via OBO flow for Maximo/SAP access."
            ),
            "username": username,
            "token_preview": token[:40] + "..." if len(token) > 40 else token,
            "pattern": "Pattern 1 - Transport Level Header Propagation"
        }
        elapsed = (time.monotonic() - t0) * 1000
        log.info(f"   → 200 OK  ({elapsed:.1f} ms)")
        return JSONResponse(result)

    log.warning("   ⚠️  No Bearer token in Authorization header")
    elapsed = (time.monotonic() - t0) * 1000
    log.info(f"   → 200 warning  ({elapsed:.1f} ms)")
    return JSONResponse({
        "status": "warning",
        "message": "⚠️ No Bearer token found in Authorization header.",
        "username": "NOT_FOUND",
        "token_preview": "NOT_FOUND"
    }, status_code=200)

# Wire up Starlette ASGI application
middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/check-identity", endpoint=handle_check_identity, methods=["GET", "POST"]),
        Mount("/messages", app=sse.handle_post_message),
    ],
    middleware=middleware
)

if __name__ == "__main__":
    log.info("━" * 56)
    log.info("🚀  WxO MCP SSE Server  —  debug mode ON")
    log.info("   Routes:")
    log.info("     GET  /sse              MCP SSE transport (native MCP clients)")
    log.info("     GET  /check-identity   REST identity check  (WxO OpenAPI tool)")
    log.info("     POST /messages         MCP message handler")
    log.info("   Listening →  http://0.0.0.0:8000")
    log.info("━" * 56)
    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level="warning")
