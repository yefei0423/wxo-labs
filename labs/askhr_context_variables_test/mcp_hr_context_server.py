# ---
# **Author**: Markus van Kempen | mvk@ca.ibm.com  
# [Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)  
# *No bug too small, no syntax too weird.*
# ---
"""
MCP SSE Server for testing WatsonX Orchestrate context variable injection.

This server validates two context-passing patterns used by the askHR_agent:

  Pattern A — LLM-mediated argument injection
    The agent's instructions contain {clientID}, {name}, {role}, {user_name},
    {email_id} placeholders. WxO substitutes the live context values before
    sending the system prompt to the LLM. The LLM then passes them as JSON
    arguments when calling POST /get-hr-context.

  Pattern B — HTTP header Bearer token (identity only)
    When the OpenAPI tool is bound to a WxO Bearer connection, Orchestrate may
    inject Authorization: Bearer <JWT> on outbound HTTPS calls to this URL.
    The handler _extract_bearer_identity() decodes the JWT payload (no
    signature verification) for logging and JSON response diagnostics.
    If no header is sent (manual curl tests, tools without credentials), logs
    show "Bearer identity: NOT_FOUND" — this does not affect Pattern A validation.

POST /get-hr-context — validation rules (implemented in _build_hr_context_response):
  • A field counts as MISSING if its value is any of:
      NOT_PROVIDED (absent key), None, "" (empty string).
  • WxO/OpenAPI serializers often omit keys OR send "". The LLM can forward
      email_id="" on a flaky turn — that yields status partial and
      "⚠️ context vars present=False" in server logs while HTTP still returns 200.

Log line meanings (grep-friendly):
  "Request body:" — exact JSON WxO POSTed after tool schema merge + LLM args.
  "✅ context vars present=True"  — all five required strings non-empty.
  "⚠️ context vars present=False" — at least one key missing/null/blank.
  "Bearer identity:" — JWT-derived username from Authorization header if present.

See README.md § "Architecture — WxO outbound tool → ngrok → local MCP" for a
diagram and sample ngrok/MCP logs from a live validation run.

Routes:
  POST /get-hr-context   REST endpoint for the OpenAPI tool (WxO calls this)
  GET  /health           Health check
  GET  /sse              MCP SSE transport endpoint (for native MCP clients)
  POST /messages         MCP message handler

Dependencies:
  pip install mcp starlette uvicorn
"""

import base64
import json as _json
import logging
import time
from contextvars import ContextVar

import uvicorn
import mcp.types as types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

# ── Structured colour logging ──────────────────────────────────────────────────
class _ColourFormatter(logging.Formatter):
    GREY = "\033[90m"; CYAN = "\033[96m"; GREEN = "\033[92m"
    YELLOW = "\033[93m"; RED = "\033[91m"; RESET = "\033[0m"
    COLOURS = {
        logging.DEBUG: "\033[90m", logging.INFO: "\033[96m",
        logging.WARNING: "\033[93m", logging.ERROR: "\033[91m",
    }
    def format(self, record):
        c = self.COLOURS.get(record.levelno, self.RESET)
        ts = self.formatTime(record, "%H:%M:%S")
        return f"{self.GREY}{ts}{self.RESET} {c}{record.levelname:<7}{self.RESET} {record.getMessage()}"

_h = logging.StreamHandler()
_h.setFormatter(_ColourFormatter())
log = logging.getLogger("hr.mcp")
log.setLevel(logging.DEBUG)
log.addHandler(_h)
log.propagate = False

# ── Bearer token context (per-request, async-safe) ────────────────────────────
wxo_token_ctx: ContextVar[str] = ContextVar("wxo_token", default="NO_BEARER_TOKEN_FOUND")


def _decode_jwt_payload(token: str) -> dict:
    """Base64-decode the JWT payload segment without signature verification."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return _json.loads(base64.b64decode(padded))
    except Exception as exc:
        log.error(f"JWT decode failed: {exc}")
        return {}


def _extract_bearer_identity(request: Request) -> dict:
    """Extract username from the Authorization header JWT."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"token_found": False, "username": "NOT_FOUND", "token_preview": "NOT_FOUND"}
    token = auth.split(" ", 1)[1]
    claims = _decode_jwt_payload(token)
    username = (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("sub")
        or "UNKNOWN"
    )
    return {
        "token_found": True,
        "username": username,
        "token_preview": token[:40] + "..." if len(token) > 40 else token,
    }


# ── MCP Server (SSE transport) ─────────────────────────────────────────────────
mcp_app = Server("hr-context-mcp-server")
sse = SseServerTransport("/messages")


@mcp_app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_hr_context",
            description=(
                "Returns HR context for a user identified by WxO context variables. "
                "Pass all five context values — clientID, name, role, user_name, email_id — "
                "exactly as received from your instructions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "clientID":   {"type": "string", "description": "Client ID from WxO context"},
                    "name":       {"type": "string", "description": "Display name from WxO context"},
                    "role":       {"type": "string", "description": "User role from WxO context"},
                    "user_name":  {"type": "string", "description": "Username from WxO context"},
                    "email_id":   {"type": "string", "description": "Email ID from WxO context"},
                },
                "required": ["clientID", "name", "role", "user_name", "email_id"],
            },
        )
    ]


@mcp_app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    log.info(f"── MCP tool call  name={name!r}  args={arguments}")
    if name == "get_hr_context":
        result = _build_hr_context_response(arguments, bearer_identity=None)
        return [types.TextContent(type="text", text=_json.dumps(result, indent=2))]
    raise ValueError(f"Unknown tool: {name}")


async def handle_sse(request: Request):
    """Intercept headers before the MCP handshake to capture the Bearer token."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        wxo_token_ctx.set(auth.split(" ", 1)[1])
        log.info("SSE connect — Bearer token captured")
    else:
        wxo_token_ctx.set("NO_BEARER_TOKEN_FOUND")
        log.warning("SSE connect — no Authorization header")

    async with sse.connect_sse(request.scope, request.receive, request._send) as endpoints:
        await mcp_app.run(endpoints[0], endpoints[1], mcp_app.create_initialization_options())
    return Response()


# ── REST endpoint (/get-hr-context) ───────────────────────────────────────────

def _build_hr_context_response(args: dict, bearer_identity: dict | None) -> dict:
    """Assemble the HR context JSON returned to the agent for POST /get-hr-context.

    Args:
        args: Tool arguments from WxO after OpenAPI deserialization. Keys may be
            missing or explicitly set to "" by the orchestration layer — both
            are treated as "not injected" for the corresponding field.
        bearer_identity: Optional dict from _extract_bearer_identity(); merged
            into payload under "bearer_identity" when non-None (REST path wires
            this only when JWT present).

    Returns:
        dict suitable for JSONResponse, including validation.missing listing
        which of clientID/name/role/user_name/email_id failed the non-empty check.
    """
    client_id  = args.get("clientID",  "NOT_PROVIDED")
    name       = args.get("name",      "NOT_PROVIDED")
    role       = args.get("role",      "NOT_PROVIDED")
    user_name  = args.get("user_name", "NOT_PROVIDED")
    email_id   = args.get("email_id",  "NOT_PROVIDED")

    all_present = all(
        v not in ("NOT_PROVIDED", "", None)
        for v in [client_id, name, role, user_name, email_id]
    )

    # WxO system variables (auto-injected — passed through if LLM forwards them)
    wxo_email_id  = args.get("wxo_email_id",  None)
    wxo_user_name = args.get("wxo_user_name", None)
    wxo_thread_id = args.get("wxo_thread_id", None)
    wxo_run_id    = args.get("wxo_run_id",    None)

    payload = {
        "status": "success" if all_present else "partial",
        "context_variables_received": {
            "clientID":  client_id,
            "name":      name,
            "role":      role,
            "user_name": user_name,
            "email_id":  email_id,
        },
        "validation": {
            "all_context_variables_present": all_present,
            "missing": [
                k for k, v in {
                    "clientID": client_id, "name": name, "role": role,
                    "user_name": user_name, "email_id": email_id,
                }.items() if v in ("NOT_PROVIDED", "", None)
            ],
        },
        "hr_summary": (
            f"HR profile loaded for {name} ({email_id}). "
            f"Role: {role}. Client: {client_id}. "
            f"Login: {user_name}."
        ) if all_present else "⚠️ Incomplete context — some variables were not injected by WxO.",
        "pattern": "Pattern A — LLM-mediated context argument injection",
        "wxo_system_vars": {
            "wxo_email_id":  wxo_email_id  or "not forwarded by LLM",
            "wxo_user_name": wxo_user_name or "not forwarded by LLM",
            "wxo_thread_id": wxo_thread_id or "not forwarded by LLM",
            "wxo_run_id":    wxo_run_id    or "not forwarded by LLM",
            "note": "System vars are in Python tool request_context; LLM only forwards them if tool schema declares them",
        },
    }

    if bearer_identity:
        payload["bearer_identity"] = bearer_identity
        payload["pattern"] += " + Pattern B — Bearer token header"

    return payload


async def handle_get_hr_context(request: Request) -> JSONResponse:
    """
    REST handler for POST /get-hr-context.

    Called by WxO when askHR invokes the imported OpenAPI tool. Parses JSON body,
    merges `_extract_bearer_identity(request)` into the payload when JWT present.

    Structured logs (grep `POST /get-hr-context` and `Request body:`):
      • `client=<ip>` — remote address (WxO egress or ngrok upstream).
      • `Bearer identity: NOT_FOUND | <username>` — from JWT only; optional.
      • `✅|⚠️ context vars present=` — mirrors `validation.all_context_variables_present`.

    Behaviour for empty-string fields (`email_id=""`) is documented inline in this
    module docstring and in README.md § Architecture — WxO → ngrok → local MCP.

    Always returns HTTP 200; semantic success/failure is in the JSON `status` and
    `validation` keys (`_build_hr_context_response`).
    """
    t0 = time.monotonic()
    client = request.client.host if request.client else "unknown"
    log.info(f"── POST /get-hr-context  client={client}")

    try:
        body = await request.json()
    except Exception:
        body = {}

    log.debug(f"   Request body: {body}")

    bearer_identity = _extract_bearer_identity(request)
    log.info(f"   Bearer identity: {bearer_identity.get('username')}")

    result = _build_hr_context_response(body, bearer_identity)
    elapsed = (time.monotonic() - t0) * 1000

    status = "✅" if result["status"] == "success" else "⚠️"
    log.info(
        f"   {status} context vars present={result['validation']['all_context_variables_present']} "
        f"({elapsed:.1f} ms)"
    )
    return JSONResponse(result)


async def handle_health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "hr-context-mcp-server"})


# ── Starlette ASGI app ─────────────────────────────────────────────────────────
middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

starlette_app = Starlette(
    routes=[
        Route("/get-hr-context", endpoint=handle_get_hr_context, methods=["POST"]),
        Route("/health",         endpoint=handle_health,         methods=["GET"]),
        Route("/sse",            endpoint=handle_sse,            methods=["GET"]),
        Mount("/messages",       app=sse.handle_post_message),
    ],
    middleware=middleware,
)

if __name__ == "__main__":
    log.info("━" * 60)
    log.info("🚀  askHR MCP Context Server")
    log.info("   Routes:")
    log.info("     POST /get-hr-context    OpenAPI tool endpoint (WxO calls this)")
    log.info("     GET  /health            Health check")
    log.info("     GET  /sse               MCP SSE transport")
    log.info("     POST /messages          MCP message handler")
    log.info("   Listening → http://0.0.0.0:8000")
    log.info("━" * 60)
    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level="warning")
