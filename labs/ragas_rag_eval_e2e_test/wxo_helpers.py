"""
Watsonx Orchestrate REST helpers for RAG / Ragas evaluation probes.

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

Patterns are copied from (not imported from) ../evaluations_test/simple_api_evaluator.py
and ../token_tracking_test/live_token_tracker.py so this folder stays self-contained.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests

from ibm_watsonx_orchestrate.cli.config import (
    AUTH_CONFIG_FILE,
    AUTH_CONFIG_FILE_FOLDER,
    AUTH_MCSP_TOKEN_OPT,
    AUTH_SECTION_HEADER,
    ENV_WXO_URL_OPT,
    Config,
)

cli_config = Config()
active_env = cli_config.get_active_env()
WXO_API_URL = cli_config.get_active_env_config(ENV_WXO_URL_OPT)

auth_cfg = Config(AUTH_CONFIG_FILE_FOLDER, AUTH_CONFIG_FILE)
WXO_TOKEN = auth_cfg.get(AUTH_SECTION_HEADER).get(active_env, {}).get(AUTH_MCSP_TOKEN_OPT)

if not WXO_TOKEN:
    raise ValueError(
        f"No token found for environment '{active_env}'. "
        f"Run: orchestrate env activate {active_env}"
    )

HEADERS = {
    "Authorization": f"Bearer {WXO_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def normalize_trace_id_for_api(raw: str | None) -> str | None:
    """32-hex trace ids often appear without hyphens; normalize for GET /v1/traces/.../spans."""
    if not raw:
        return None
    s = str(raw).strip().lower().replace("-", "")
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return s
    return str(raw).strip()


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _deep_walk_toolmessage_contents(root: Any, out: list[str], depth: int = 0) -> None:
    if depth > 40:
        return
    if isinstance(root, str):
        s = root.strip()
        if len(s) > 120 and s[:1] in "{[":
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                return
            _deep_walk_toolmessage_contents(parsed, out, depth + 1)
        return
    if isinstance(root, dict):
        mid = root.get("id")
        if isinstance(mid, list) and "ToolMessage" in mid:
            kwargs = root.get("kwargs") or {}
            c = kwargs.get("content")
            if isinstance(c, str) and len(c.strip()) > 10:
                out.append(c.strip())
        for v in root.values():
            _deep_walk_toolmessage_contents(v, out, depth + 1)
    elif isinstance(root, list):
        for v in root:
            _deep_walk_toolmessage_contents(v, out, depth + 1)


def tool_message_contents_from_trace(trace_payload: dict[str, Any] | None) -> list[str]:
    """
    Extract LangChain-serialized ToolMessage `content` strings from Traceloop span attributes.

    This matches WxO traces where tool/RAG output appears under traceloop.entity.input/output
    (often nested JSON strings).
    """
    if not trace_payload:
        return []
    found: list[str] = []
    for span in extract_spans(trace_payload):
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            if key not in ("traceloop.entity.input", "traceloop.entity.output"):
                continue
            val = attr.get("value", {})
            s = _otlp_attribute_scalar_string(val if isinstance(val, dict) else {})
            if not s or len(s) < 30:
                continue
            _deep_walk_toolmessage_contents(s, found)
    return _dedupe_preserve(found)


def split_tool_output_into_passages(text: str) -> list[str]:
    """If the tool returns multiple [DOC n ...] blocks, split for per-chunk Ragas contexts."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?=\[DOC\s*\d+)", text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [text]


def filter_contexts_for_ragas(contexts: list[str], user_prompt: str) -> list[str]:
    """
    Drop trace/thread artefacts that are not retrieval text (Ragas judges penalize them).

    - Exact echo of the user question (often the tool `topic` string in a ToolMessage).
    - WxO "configuring your tool …" placeholders.
    - If any chunk looks like ``[DOC …]`` stub output, keep only those chunks so the user
      question does not appear as a fake "context".
    """
    if not contexts:
        return contexts
    q = (user_prompt or "").strip()
    ql = q.lower()
    cleaned: list[str] = []
    for raw in contexts:
        c = raw.strip()
        if not c:
            continue
        cl = c.lower()
        if ql and cl == ql:
            continue
        if "configuring your tool in the background" in cl:
            continue
        cleaned.append(c)
    if not cleaned:
        return contexts
    docish = [c for c in cleaned if "[doc" in c.lower()]
    if docish:
        return _dedupe_preserve(docish)
    return _dedupe_preserve(cleaned)


def contexts_for_ragas_eval(
    messages: list[dict[str, Any]],
    trace_payload: dict[str, Any] | None,
    *,
    assistant_answer: str,
    user_prompt: str = "",
    split_passages: bool = False,
) -> list[str]:
    """
    Prefer trace ToolMessage bodies (tool / document RAG), else fall back to thread blobs.

    Drops thread blobs that duplicate the final assistant answer.
    """
    ctx: list[str] = []
    from_trace = tool_message_contents_from_trace(trace_payload)
    if from_trace:
        ctx = list(from_trace)
    else:
        ans_l = (assistant_answer or "").strip().lower()
        for c in candidate_contexts_from_thread_messages(messages):
            cl = c.strip()
            if len(cl) < 40:
                continue
            if ans_l and cl.lower() == ans_l:
                continue
            ctx.append(cl)
        ctx = _dedupe_preserve(ctx)

    ctx = filter_contexts_for_ragas(ctx, user_prompt)

    if split_passages and len(ctx) == 1:
        ctx = split_tool_output_into_passages(ctx[0])
    elif split_passages:
        expanded: list[str] = []
        for c in ctx:
            expanded.extend(split_tool_output_into_passages(c))
        ctx = _dedupe_preserve(expanded)
    else:
        return ctx

    ctx = filter_contexts_for_ragas(ctx, user_prompt)
    return ctx


def run_chat_turn_collect_contexts(
    agent_name: str,
    user_prompt: str,
    *,
    use_trace: bool = True,
    poll_attempts: int = 12,
    poll_delay_s: float = 3.0,
    thread_settle_s: float = 2.0,
    split_passages: bool = False,
) -> dict[str, Any]:
    """
    One full Orchestrate turn: chat/completions → thread messages → optional trace poll → contexts.

    Use this to build Ragas rows (question, answer, contexts) from a document/RAG agent that
    surfaces retrieval via tools (native KB may still fall back to thread heuristics only).
    """
    agent_id = get_agent_id_by_name(agent_name)
    body, hdr = chat_completions(agent_id, user_prompt)
    answer = assistant_answer_from_chat_body(body)
    thread_id = body.get("thread_id")
    trace_raw = hdr.get("trace_id_header") or body.get("trace_id")
    trace_id_norm = normalize_trace_id_for_api(trace_raw)

    time.sleep(max(0.0, thread_settle_s))
    messages: list[dict[str, Any]] = []
    if thread_id:
        messages = get_thread_messages(thread_id)

    trace_payload: dict[str, Any] | None = None
    if use_trace and trace_id_norm:
        trace_payload = poll_trace_spans(
            trace_id_norm,
            attempts=poll_attempts,
            delay_s=poll_delay_s,
        )

    contexts = contexts_for_ragas_eval(
        messages,
        trace_payload,
        assistant_answer=answer,
        user_prompt=user_prompt,
        split_passages=split_passages,
    )

    return {
        "question": user_prompt,
        "answer": answer,
        "contexts": contexts,
        "thread_id": thread_id,
        "trace_id": trace_id_norm,
        "tools_from_thread": tools_invoked_from_thread_messages(messages),
        "trace_span_count": len(list(extract_spans(trace_payload))) if trace_payload else 0,
    }


def get_agent_id_by_name(agent_name: str) -> str:
    url = f"{WXO_API_URL.rstrip('/')}/v1/orchestrate/agents"
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    for agent in response.json():
        if agent.get("name") == agent_name:
            return agent["id"]
    raise ValueError(f"Agent '{agent_name}' not found.")


def chat_completions(
    agent_id: str,
    user_text: str,
    *,
    stream: bool = False,
    extra_messages: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """
    OpenAI-style orchestrate chat. Returns (json_body, capture_headers).
    capture_headers: trace_id from W3C traceparent (if present), raw traceparent.
    """
    messages: list[dict[str, str]] = list(extra_messages or [])
    messages.append({"role": "user", "content": user_text})
    payload = {"messages": messages, "stream": stream}
    url = f"{WXO_API_URL.rstrip('/')}/v1/orchestrate/{agent_id}/chat/completions"
    response = requests.post(url, headers=HEADERS, json=payload, timeout=600)
    response.raise_for_status()
    traceparent = response.headers.get("traceparent")
    trace_id: str | None = None
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 2:
            trace_id = parts[1]
    capture = {
        "traceparent": traceparent,
        "trace_id_header": trace_id,
    }
    return response.json(), capture


def get_thread_messages(thread_id: str) -> list[dict[str, Any]]:
    url = f"{WXO_API_URL.rstrip('/')}/v1/orchestrate/threads/{thread_id}/messages"
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    return response.json()


def extract_spans(trace_data: dict[str, Any]):
    """Yield OTLP spans from GET /v1/traces/{id}/spans response."""
    resource_spans = trace_data.get("traceData", {}).get("resourceSpans", [])
    for rs in resource_spans:
        for scope_span in rs.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                yield span


def poll_trace_spans(
    trace_id: str,
    *,
    attempts: int = 10,
    delay_s: float = 3.0,
) -> dict[str, Any] | None:
    """Observability spans are asynchronous; poll like token_tracking_test."""
    url = f"{WXO_API_URL.rstrip('/')}/v1/traces/{trace_id}/spans"
    last = None
    for _ in range(attempts):
        response = requests.get(url, headers=HEADERS, timeout=120)
        if response.status_code == 200:
            last = response.json()
            spans = list(extract_spans(last))
            if spans:
                return last
        time.sleep(delay_s)
    return last


def _flatten_strings(obj: Any, out: list[str], max_depth: int = 12) -> None:
    if max_depth <= 0:
        return
    if isinstance(obj, str):
        text_obj = obj.strip()
        if len(text_obj) > 40:
            out.append(text_obj)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            # Prefer bodies that often hold tool / retriever output
            if k in (
                "content",
                "text",
                "output",
                "result",
                "message",
                "body",
                "observation",
                "tool_output",
                "documents",
                "chunks",
                "context",
                "contexts",
                "retrieved_context",
            ):
                _flatten_strings(v, out, max_depth - 1)
            else:
                _flatten_strings(v, out, max_depth - 1)
    elif isinstance(obj, list):
        for item in obj:
            _flatten_strings(item, out, max_depth - 1)


def candidate_contexts_from_thread_messages(messages: list[dict[str, Any]]) -> list[str]:
    """
    Best-effort extraction of text blobs that might be retrieved knowledge or tool output.

    WxO does not document a stable field for "RAG chunks" on this endpoint; structure
    varies by agent (native KB vs custom search tool vs collaborator). Treat results
    as *candidates* and inspect raw JSON when tuning Ragas.
    """
    collected: list[str] = []
    for msg in messages:
        if msg.get("step_history"):
            for step in msg["step_history"]:
                for detail in step.get("step_details", []):
                    _flatten_strings(detail, collected)
        if msg.get("role") == "assistant" and msg.get("content"):
            for block in msg["content"]:
                _flatten_strings(block, collected)
    # De-dupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in collected:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def prompt_like_strings_from_spans(trace_payload: dict[str, Any]) -> list[str]:
    """Collect long gen_ai / prompt attributes from OTLP spans (may include grounded context)."""
    out: list[str] = []
    for span in extract_spans(trace_payload):
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            val = attr.get("value", {})
            s = val.get("stringValue")
            if not s and val.get("arrayValue"):
                continue
            if not isinstance(s, str):
                continue
            if not ("prompt" in key or "context" in key or key.startswith("gen_ai.")):
                continue
            if len(s.strip()) > 80:
                out.append(s.strip())
    return out


def _otlp_attribute_scalar_string(val: dict[str, Any]) -> str | None:
    """Best-effort: get a string from an OTLP AnyValue-style JSON object."""
    if not val:
        return None
    s = val.get("stringValue")
    if isinstance(s, str):
        return s
    iv = val.get("intValue")
    if iv is not None:
        return str(iv)
    bv = val.get("boolValue")
    if bv is not None:
        return str(bv)
    av = val.get("arrayValue")
    if av and isinstance(av.get("values"), list):
        parts: list[str] = []
        for item in av["values"]:
            if not isinstance(item, dict):
                continue
            inner = _otlp_attribute_scalar_string(item)
            if inner:
                parts.append(inner)
        if parts:
            return "\n".join(parts)
    return None


def _is_interesting_rag_attr_key(key: str) -> bool:
    """Heuristic: attributes that often carry prompts, tools, or injected context."""
    kl = key.lower()
    needles = (
        "gen_ai",
        "llm.",
        "traceloop",
        "prompt",
        "completion",
        "input",
        "output",
        "message",
        "tool",
        "retriev",
        "document",
        "chunk",
        "knowledge",
        "embedding",
        "vector",
        "invocation",
        "entity.",
        "workflow.",
    )
    return any(n in kl for n in needles)


def analyze_trace_for_rag(
    trace_payload: dict[str, Any],
    *,
    min_string_len: int = 80,
    max_records: int = 40,
) -> dict[str, Any]:
    """
    Summarize span attributes that might help reconstruct RAG / tool context.

    Returns counts, top attribute keys, and long string snippets for operators.
    """
    span_count = 0
    span_names: list[str] = []
    key_counter: Counter[str] = Counter()
    records: list[dict[str, Any]] = []

    for span in extract_spans(trace_payload):
        span_count += 1
        name = span.get("name") or ""
        if name and name not in span_names:
            span_names.append(name)
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            if not key:
                continue
            key_counter[key] += 1
            if not _is_interesting_rag_attr_key(key):
                continue
            raw_val = attr.get("value", {})
            text = _otlp_attribute_scalar_string(raw_val if isinstance(raw_val, dict) else {})
            if not text or len(text.strip()) < min_string_len:
                continue
            t = text.strip()
            records.append(
                {
                    "span_name": name,
                    "key": key,
                    "length": len(t),
                    "preview": t[:400] + ("…" if len(t) > 400 else ""),
                }
            )
            if len(records) >= max_records:
                break

    return {
        "span_count": span_count,
        "span_names": span_names[:30],
        "top_attribute_keys": dict(key_counter.most_common(25)),
        "interesting_long_strings": records,
    }


def trace_blob_for_overlap(trace_payload: dict[str, Any], *, min_string_len: int = 60) -> str:
    """Single lowercase blob of all interesting long attribute strings (for crude matching)."""
    parts: list[str] = []
    for span in extract_spans(trace_payload):
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            if not _is_interesting_rag_attr_key(key):
                continue
            val = attr.get("value", {})
            text = _otlp_attribute_scalar_string(val if isinstance(val, dict) else {})
            if text and len(text.strip()) >= min_string_len:
                parts.append(text.strip())
    return "\n".join(parts).lower()


def thread_trace_overlap_report(
    thread_contexts: list[str],
    trace_payload: dict[str, Any] | None,
    *,
    snippet_len: int = 72,
) -> dict[str, Any]:
    """
    See whether distinctive slices of thread-derived contexts appear inside trace text.

    Useful to decide if observability alone could feed Ragas `contexts` for an agent.
    """
    if not trace_payload:
        return {
            "trace_available": False,
            "matched_thread_blobs": 0,
            "total_thread_blobs": len(thread_contexts),
            "fraction": 0.0,
            "notes": "No span payload (poll failed, wrong trace_id, or permissions).",
        }

    blob = trace_blob_for_overlap(trace_payload)
    if not blob:
        return {
            "trace_available": True,
            "matched_thread_blobs": 0,
            "total_thread_blobs": len(thread_contexts),
            "fraction": 0.0,
            "notes": "Spans present but no long 'interesting' string attributes matched heuristics.",
        }

    blobs = [c.strip() for c in thread_contexts if len(c.strip()) >= 100]
    if not blobs:
        return {
            "trace_available": True,
            "matched_thread_blobs": 0,
            "total_thread_blobs": 0,
            "fraction": 0.0,
            "notes": "No thread blobs long enough to compare (>=100 chars).",
        }

    matched = 0
    details: list[dict[str, Any]] = []
    for i, c in enumerate(blobs):
        c_low = c.lower()
        start = max(0, (len(c_low) - snippet_len) // 3)
        snippet = c_low[start : start + snippet_len]
        if not snippet:
            continue
        ok = snippet in blob
        if ok:
            matched += 1
        details.append({"thread_blob_index": i, "snippet": snippet[:snippet_len], "found_in_trace": ok})

    return {
        "trace_available": True,
        "matched_thread_blobs": matched,
        "total_thread_blobs": len(blobs),
        "fraction": matched / len(blobs) if blobs else 0.0,
        "per_blob": details[:15],
        "notes": "Fraction of long thread blobs whose substring appears in concatenated trace text.",
    }


def fetch_trace_spans_response(trace_id: str) -> tuple[int, dict[str, Any] | None]:
    """Single GET without polling; returns (http_status, json_or_none)."""
    url = f"{WXO_API_URL.rstrip('/')}/v1/traces/{trace_id}/spans"
    response = requests.get(url, headers=HEADERS, timeout=120)
    if response.status_code != 200:
        return response.status_code, None
    return response.status_code, response.json()


def load_trace_export_json(path: str) -> dict[str, Any]:
    """Load JSON from `orchestrate observability traces export -o file.json` (or REST spans payload)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tool_contexts_from_trace_export_file(path: str, *, split_passages: bool = False) -> list[str]:
    """Extract ToolMessage text from a CLI-exported trace file."""
    payload = load_trace_export_json(path)
    ctx = tool_message_contents_from_trace(payload)
    if split_passages and len(ctx) == 1:
        return split_tool_output_into_passages(ctx[0])
    if split_passages:
        expanded: list[str] = []
        for c in ctx:
            expanded.extend(split_tool_output_into_passages(c))
        return _dedupe_preserve(expanded)
    return ctx


def cli_trace_export_complete_enough(path: str) -> bool:
    """
    True if exported JSON likely includes tool/RAG spans (not an early partial trace).

    The Observability export can succeed before all child spans are persisted; wait until
    ToolMessage or tools.task appears, otherwise Ragas context extraction returns [].
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return False
    if "ToolMessage" in text:
        return True
    if '"tools.task"' in text or "tools.task" in text:
        return True
    if "ragas_retrieve_stub.tool" in text:
        return True
    return False


def assistant_answer_from_chat_body(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return msg.get("content") or ""


def tools_invoked_from_thread_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Collect tool names from step_history (same idea as evaluations_test/simple_api_evaluator)."""
    names: list[str] = []
    for msg in messages:
        if not msg.get("step_history"):
            continue
        for step in msg["step_history"]:
            for detail in step.get("step_details", []):
                if detail.get("type") not in ("tool_calls", "tool_call"):
                    continue
                calls = detail.get("tool_calls")
                if calls is None:
                    calls = [detail]
                elif not isinstance(calls, list):
                    calls = [calls]
                for call in calls:
                    if isinstance(call, dict):
                        n = call.get("name") or (call.get("function") or {}).get("name")
                        if n:
                            names.append(n)
    return names
