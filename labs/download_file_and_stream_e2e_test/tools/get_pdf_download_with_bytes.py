# Author: Markus van Kempen | mvk@ca.ibm.com
# Research: https://pages.github.ibm.com/mvankempen/homepage/
"""WxO Python tool: PDF download helpers for chat (HTTPS anchor; optional inlined ``data:`` RFC 2397).

**Default behaviour** returns only a short **HTTPS** `<a>` + Plain URL (**no HTTP fetch**, no base64)—
so assistants using **Groq** (and similar tight context windows) never receive ~1 MiB of **`data:`**
text in tool output.

Set **`PDF_DOWNLOAD_INCLUDE_DATA_URI=1`** when you deliberately want chunked HTTPS fetch plus a
large **`data:application/pdf;base64,...`** `<a>` (may exceed LLM/request limits unless you also
raise limits or shrink ``PDF_DOWNLOAD_MAX_BYTES`` / use a tiny ``PDF_SOURCE_URL``).

Streaming fetch lives in **_fetch_pdf** (chunked reads). Local demo without ADK:
``examples/streaming_pdf_fetch_demo.py``. See README for IBM doc links."""


from __future__ import annotations

import base64
import html as html_lib
import os
import re
import urllib.error
import urllib.request

from ibm_watsonx_orchestrate.agent_builder.tools import tool


# Public sample URL (PRIMARY only unless PDF_DOWNLOAD_INCLUDE_DATA_URI=1, which fetches ~1 MiB).
DEFAULT_SOURCE_URL = (
    "https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf"
)
DEFAULT_DOWNLOAD_NAME = "compressed.tracemonkey-pldi-09.pdf"
DEFAULT_LINK_TEXT = "Public sample PDF"
# Tracemonkey demo GET is ~1016315 Content-Length — 1 MiB cap fits with small slack.
DEFAULT_DOWNLOAD_MAX_BYTES = 1_048_576
DEFAULT_ANCHOR_ID = "pdfDataDownload"


def _include_data_uri() -> bool:
    """RFC 2397 embedding is optional — default off to avoid exploding chat / Groq ``messages`` size."""

    v = (os.getenv("PDF_DOWNLOAD_INCLUDE_DATA_URI") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _safe_id(raw: str) -> str:
    s = (raw or "").strip() or DEFAULT_ANCHOR_ID
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", s):
        return s
    return DEFAULT_ANCHOR_ID


def _fetch_pdf(url: str, max_bytes: int) -> bytes:
    """Stream read from HTTP(S) response in chunks (no single giant ``read()``)."""

    chunk_size = min(65536, max(max_bytes + 1, 1))
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "download-file-and-stream-e2e/1 WxO-python-tool"},
    )
    buf = bytearray()
    with urllib.request.urlopen(req, timeout=60) as resp:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise ValueError(
                    f"Response exceeded PDF_DOWNLOAD_MAX_BYTES ({max_bytes}); "
                    "use a smaller file or HTTPS link pattern instead."
                )
    return bytes(buf)


@tool
def get_pdf_download_with_bytes() -> str:
    """Return HTML for a hosted PDF URL.

    **Default:** **PRIMARY** only — HTTPS ``<a>`` + **Plain URL:** (tiny tool string; safe for Groq).

    **Opt-in SECONDARY:** set ``PDF_DOWNLOAD_INCLUDE_DATA_URI=1`` — then this tool HTTPS-fetches bytes
    and appends ``data:application/pdf;base64,...`` (**very large**; may exceed provider limits).

    Env (optional):

        PDF_DOWNLOAD_INCLUDE_DATA_URI — ``1``/``true`` to fetch + emit ``data:`` anchor (default: off).

        PDF_SOURCE_URL           — HTTPS URL (default Mozilla pdf.js tracemonkey demo).
        PDF_DOWNLOAD_MAX_BYTES   — fetch cap when data URI enabled (default **1048576**).
        PDF_DOWNLOAD_FILENAME  — ``download`` on SECONDARY `<a>` (default demo filename).
        PDF_DOWNLOAD_LABEL       — SECONDARY link label (default **Public sample PDF**).
        PDF_DOWNLOAD_LINK_ID     — HTML ``id`` (default ``pdfDataDownload``).
    """
    url = (os.getenv("PDF_SOURCE_URL") or "").strip() or DEFAULT_SOURCE_URL
    max_bytes = int(
        (os.getenv("PDF_DOWNLOAD_MAX_BYTES") or "").strip()
        or str(DEFAULT_DOWNLOAD_MAX_BYTES)
    )
    fname = (os.getenv("PDF_DOWNLOAD_FILENAME") or "").strip() or DEFAULT_DOWNLOAD_NAME
    label_text = (
        (os.getenv("PDF_DOWNLOAD_LABEL") or "").strip() or DEFAULT_LINK_TEXT
    )
    dom_id = _safe_id(os.getenv("PDF_DOWNLOAD_LINK_ID", DEFAULT_ANCHOR_ID))

    esc_url_https = html_lib.escape(url, quote=True)
    esc_fname = html_lib.escape(fname, quote=True)
    esc_label = html_lib.escape(label_text, quote=False)
    esc_id = html_lib.escape(dom_id, quote=False)

    fallback_anchor = (
        f'<a href="{esc_url_https}" id="{esc_id}-https" '
        f'target="_blank" rel="noopener noreferrer">Same PDF via HTTPS</a>'
    )
    plain = html_lib.escape(url)

    https_block = (
        "PRIMARY (HTTPS · best chance of a real hyperlink in WxO):\n\n"
        f"{fallback_anchor}\n"
        f"Plain URL: {plain}"
    )

    if not _include_data_uri():
        footer = (
            "\nNOTE: Inlined RFC 2397 ``data:application/pdf`` bytes are **disabled** "
            "(set **PDF_DOWNLOAD_INCLUDE_DATA_URI=1** on the tool to embed; avoids huge LLM payloads). "
            "Use **PRIMARY** to open/download via HTTPS.\n"
        )
        return f"{https_block}{footer}"

    try:
        pdf_bytes = _fetch_pdf(url, max_bytes=max_bytes)
    except ValueError as e:
        return f"TOOL_ERROR (size): {e}"
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return f"TOOL_ERROR (fetch): {type(e).__name__}: {e}"

    if not pdf_bytes.startswith(b"%PDF"):
        # Still allow uncommon generators; warn but embed.
        pass

    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    data_href = f"data:application/pdf;base64,{b64}"

    esc_href = html_lib.escape(data_href, quote=True)

    anchor = (
        f'<a id="{esc_id}" download="{esc_fname}" href="{esc_href}" '
        f'target="_blank" rel="noopener noreferrer">{esc_label}</a>'
    )
    data_block = (
        "SECONDARY (same PDF inlined RFC 2397 ``data:application/pdf;base64``):\n\n"
        f"{anchor}"
    )
    return f"{https_block}\n\n{data_block}\n"
