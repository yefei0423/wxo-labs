"""
render_images_fixed.py
======================
Fixed version of the user's MCP tool.

KEY CHANGE: Replaced `connections.key_value()` (Python tool SDK — does NOT work
in MCP context) with `os.environ` (the correct mechanism for MCP tools).

When registered with:
  orchestrate toolkits add --kind mcp --app-id "render_images" ...

WxO will inject the key-value credentials from the 'render_images' connection
directly as environment variables into this process at startup.

Author: Markus van Kempen | mvk@ca.ibm.com
"""

import os
import requests
import urllib3
from dotenv import load_dotenv  # for local dev fallback only
from mcp.server.fastmcp import FastMCP

# Load .env for local development. In WxO, env vars are injected by the platform
# and take precedence. This load_dotenv() call is a no-op when WxO has already
# set the variables.
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

mcp = FastMCP("Render Signed Images Tool")

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg"}


def get_watsonx_creds() -> dict:
    """
    Fetch credentials from environment variables.

    When running under WxO with --app-id "render_images", these are injected
    automatically from the key_value connection configured via:
        orchestrate connections set-credentials -a render_images --env draft \
          -e "BASE_URL=..." -e "USER_NAME=..." ...

    For local dev, set them in a .env file in this directory.
    """
    required_keys = ["BASE_URL", "USER_NAME", "API_KEY", "IMAGE_ANALYSIS_DEPLOYMENT_ID"]
    creds = {k: os.environ.get(k) for k in required_keys}
    missing = [k for k, v in creds.items() if not v]

    if missing:
        raise KeyError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Locally: add them to .env. In WxO: check your 'orchestrate connections set-credentials' command."
        )

    return creds


def get_auth_token(base_url: str, username: str, api_key: str) -> str:
    """Get CP4D authentication token."""
    auth_response = requests.post(
        f'{base_url}/icp4d-api/v1/authorize',
        json={"username": username, "api_key": api_key},
        verify=False,
        timeout=30
    )
    auth_response.raise_for_status()
    return f"Bearer {auth_response.json()['token']}"


def list_s3_files_under_prefix(s3_prefix: str, token: str, base_url: str) -> list[str]:
    """List all file keys under the given S3 prefix."""
    if not s3_prefix.endswith("/"):
        s3_prefix = s3_prefix + "/"

    headers = {"Content-Type": "application/json", "Authorization": token}
    params = {"prefix": s3_prefix, "limit": 1000}

    response = requests.get(
        f"{base_url}/icp4d-api/v1/assets",
        headers=headers,
        params=params,
        verify=False,
        timeout=60,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to list files under prefix '{s3_prefix}': "
            f"HTTP {response.status_code} — {response.text}"
        )

    data = response.json()
    resources = data.get("resources") or data.get("assets") or data.get("results") or []

    return [
        item.get("path") or item.get("key") or item.get("name")
        for item in resources
        if (item.get("path") or item.get("key") or item.get("name"))
        and not (item.get("path") or item.get("key") or item.get("name", "")).endswith("/")
    ]


def filter_image_files(file_keys: list[str]) -> tuple[list[str], list[str]]:
    """Split file keys into image files and non-image files."""
    image_files, skipped_files = [], []
    for key in file_keys:
        dot_index = key.rfind(".")
        ext = key[dot_index:].lower() if dot_index != -1 else ""
        (image_files if ext in SUPPORTED_IMAGE_EXTENSIONS else skipped_files).append(key)
    return image_files, skipped_files


@mcp.tool()
def debug_env_vars() -> dict:
    """
    DEBUG: Lists environment variables visible to this MCP subprocess (masked).
    """
    env_snapshot = {
        k: (v[:25] + "..." if len(v) > 25 else "[SET]")
        for k, v in sorted(os.environ.items())
        if k not in ("PATH", "PYTHONPATH", "HOME", "USER", "SHELL", "TERM")
    }
    return {"total_vars": len(env_snapshot), "vars": env_snapshot}



@mcp.tool()
def render_signed_images(s3_prefix: str) -> dict:
    """
    Analyze all chart/graph images in an S3 bucket folder using a vision model.

    Args:
        s3_prefix: The S3 prefix/path to scan for image files.

    Returns:
        dict: Analysis results from the vision model.
    """
    try:
        # ✅ FIXED: Read from environment variables (injected by WxO from key_value connection)
        creds = get_watsonx_creds()
        base_url = creds["BASE_URL"]
        username = creds["USER_NAME"]
        api_key = creds["API_KEY"]
        image_analysis_deployment_id = creds["IMAGE_ANALYSIS_DEPLOYMENT_ID"]

        token = get_auth_token(base_url, username, api_key)

        try:
            all_files = list_s3_files_under_prefix(s3_prefix, token, base_url)
        except RuntimeError as list_err:
            print(f"[WARNING] File listing failed: {list_err}. Falling back to direct prefix submission.")
            all_files = None

        if all_files is not None:
            image_files, skipped_files = filter_image_files(all_files)

            print(f"[INFO] Total files found   : {len(all_files)}")
            print(f"[INFO] Image files         : {len(image_files)} → {image_files}")
            print(f"[INFO] Skipped (non-image) : {len(skipped_files)} → {skipped_files}")

            if not image_files:
                return {
                    "success": False,
                    "error": "No supported image files found under the given prefix.",
                    "prefix_checked": s3_prefix,
                    "all_files_found": all_files,
                    "skipped_files": skipped_files,
                    "supported_formats": sorted(SUPPORTED_IMAGE_EXTENSIONS),
                }
            values = [[f] for f in image_files]
        else:
            values = [[s3_prefix]]
            skipped_files = []
            image_files = None

        payload = {"input_data": [{"values": values}]}
        headers = {"Content-Type": "application/json", "Authorization": token}
        scoring_url = (
            f"{base_url}/ml/v4/deployments/{image_analysis_deployment_id}"
            f"/predictions?version=2023-05-29"
        )

        response = requests.post(scoring_url, json=payload, headers=headers, verify=False, timeout=300)

        if response.status_code == 200:
            result = response.json()
            try:
                markdown_output = result["predictions"][0]["values"][0][0]
            except (KeyError, IndexError, TypeError):
                markdown_output = str(result)

            return {
                "success": True,
                "result": markdown_output,
                "_file_audit": {
                    "prefix": s3_prefix,
                    "total_files_found": len(all_files) if all_files is not None else "unknown (fallback mode)",
                    "image_files_processed": image_files or "unknown (fallback mode)",
                    "skipped_non_image_files": skipped_files,
                }
            }
        else:
            return {
                "success": False,
                "error": f"API call failed with status {response.status_code}",
                "details": response.text,
            }

    except KeyError as e:
        # Credential config error — surface clearly
        return {"success": False, "error": f"Credential configuration error: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Quick credential check before starting the server
    print("🔍 Checking credentials from environment...")
    try:
        creds = get_watsonx_creds()
        print(f"✅ Credentials found: BASE_URL={creds['BASE_URL'][:30]}...")
    except KeyError as e:
        print(f"⚠️  {e}")
        print("   → Set them in .env for local testing, or via WxO connections for deployment.")

    mcp.run()
