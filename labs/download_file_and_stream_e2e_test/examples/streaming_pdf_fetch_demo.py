#!/usr/bin/env python3
# Author: Markus van Kempen | mvk@ca.ibm.com
"""Local streaming fetch demo — same chunked pattern as ``tools/get_pdf_download_with_bytes.py``.

Runs without the WxO ADK package. Validates network + chunked read.

    cd download_file_and_stream_e2e_test
    python3 examples/streaming_pdf_fetch_demo.py

Optional env:

    STREAM_DEMO_URL  — HTTPS URL (default Mozilla pdf.js tracemonkey demo PDF)
    STREAM_DEMO_MAX_BYTES — cap body size (default 1048576)
"""

from __future__ import annotations

import os

CHUNK_BYTES = 64 * 1024
DEFAULT_URL = (
    "https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf"
)
DEFAULT_MAX_BYTES = 1_048_576  # Same ceiling as WxO tool (fits tracemonkey demo ~1016315 bytes)


def streaming_fetch_bounded(url: str, *, max_bytes: int, chunk_size: int = CHUNK_BYTES) -> bytes:
    from urllib.request import Request, urlopen

    cs = min(chunk_size, max(max_bytes, 1))
    req = Request(
        url,
        headers={
            "User-Agent": (
                "streaming-pdf-fetch-demo/download-file-and-stream-e2e-examples/1"
            )
        },
    )
    buf = bytearray()
    with urlopen(req, timeout=60) as resp:
        while True:
            chunk = resp.read(cs)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise ValueError(
                    f"Response exceeded STREAM_DEMO_MAX_BYTES ({max_bytes})."
                )
    return bytes(buf)


def main() -> None:
    url = (os.environ.get("STREAM_DEMO_URL") or "").strip() or DEFAULT_URL
    mx = int((os.environ.get("STREAM_DEMO_MAX_BYTES") or "").strip() or str(DEFAULT_MAX_BYTES))
    payload = streaming_fetch_bounded(url, max_bytes=mx)
    pdf_sig = payload[:8] if len(payload) >= 8 else payload
    print(f"OK: chunked fetch {len(payload)} bytes from URL (prefix {pdf_sig!r})")


if __name__ == "__main__":
    main()
