"""
probe_mcp_server.py  (STDIO mode)
===================================
Minimal FastMCP probe server running in STDIO transport.

WxO registers this via:
  orchestrate toolkits add --kind mcp --command "python probe_mcp_server.py" \
      --package-root . --app-id probe-render-images

WxO then spawns it as a subprocess and injects the key_value connection
credentials as environment variables. This tool reports back whatever
env vars it received — proving the injection works.

Author: Markus van Kempen | mvk@ca.ibm.com
"""

import os
from fastmcp import FastMCP

# For local dev testing outside WxO: load .env so we can run standalone
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

mcp = FastMCP("Connection Probe MCP")

# The exact keys set via: orchestrate connections set-credentials -e "KEY=value"
EXPECTED_KEYS = [
    "BASE_URL",
    "USER_NAME",
    "API_KEY",
    "IMAGE_ANALYSIS_DEPLOYMENT_ID",
]


@mcp.tool()
def check_credential_injection() -> dict:
    """
    Checks whether WxO correctly injected the key_value connection
    credentials as environment variables into this MCP subprocess.

    Call this tool to verify the --app-id connection wiring works before
    deploying the real image analysis tool.
    """
    found = {}
    missing = []

    for key in EXPECTED_KEYS:
        val = os.environ.get(key)
        if val:
            found[key] = val[:15] + "..." if len(val) > 15 else "[SET]"
        else:
            missing.append(key)

    injection_success = len(missing) == 0

    return {
        "injection_success": injection_success,
        "summary": (
            "All credentials injected correctly by WxO connection."
            if injection_success
            else f"Missing {len(missing)} credential(s): {missing}"
        ),
        "credentials_found": found,
        "credentials_missing": missing,
    }


@mcp.tool()
def list_all_injected_env_vars() -> dict:
    """
    DEBUG: Lists all environment variables visible to this MCP subprocess.
    Use this to see exactly what WxO injected. Remove from production.
    """
    env_snapshot = {
        k: (v[:40] + "..." if len(v) > 40 else v)
        for k, v in sorted(os.environ.items())
        if not k.startswith("_")
        and k not in ("PATH", "PYTHONPATH", "HOME", "USER", "SHELL", "TERM", "LANG")
    }
    return {
        "total_env_vars": len(env_snapshot),
        "env_vars": env_snapshot,
    }


if __name__ == "__main__":
    # STDIO mode: WxO spawns this process and communicates via stdin/stdout
    mcp.run()  # defaults to stdio transport
