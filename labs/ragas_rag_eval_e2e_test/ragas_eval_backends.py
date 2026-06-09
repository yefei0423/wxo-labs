"""
Optional Ragas LLM/embeddings backends (OpenAI defaults vs watsonx.ai judge).

Author: Markus van Kempen | mvk@ca.ibm.com
[Research | Floor 7½ 🏢🤏](https://pages.github.ibm.com/mvankempen/homepage/)
No bug too small, no syntax too weird.

watsonx path follows IBM guidance:
https://www.ibm.com/think/tutorials/ragas-rag-evaluation-python-watsonx
Install optional deps: pip install -r requirements-ragas-watsonx.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

BackendName = Literal["openai", "watsonx"]


def load_repo_dotenv() -> None:
    """
    Load test_tools/.env (or ragas_rag_eval_e2e_test/.env) if present.
    Does not override variables already set in the process environment.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent
    for p in (here.parent / ".env", here / ".env"):
        if p.is_file():
            load_dotenv(p, override=False)
            return


def _first_env(*keys: str) -> str | None:
    for k in keys:
        v = os.environ.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None


def _watsonx_url() -> str | None:
    return _first_env("WATSONX_URL", "WX_AI_URL", "watsonx_url")


def _watsonx_apikey() -> str | None:
    return _first_env("WATSONX_APIKEY", "WATSONX_API_KEY", "watsonx_api_key")


def _watsonx_project_id() -> str | None:
    return _first_env("WATSONX_PROJECT_ID", "watsonx_project_id")


def detect_ragas_backend(preference: str) -> BackendName | None:
    """
    preference: 'auto' | 'openai' | 'watsonx'
    Returns None if auto cannot resolve credentials.
    """
    p = preference.strip().lower()
    wx_ok = bool(_watsonx_apikey() and _watsonx_project_id() and _watsonx_url())
    oai_ok = bool(os.environ.get("OPENAI_API_KEY"))

    if p == "watsonx":
        return "watsonx" if wx_ok else None
    if p == "openai":
        return "openai" if oai_ok else None
    # auto
    if wx_ok:
        return "watsonx"
    if oai_ok:
        return "openai"
    return None


def build_evaluate_kwargs(backend: BackendName) -> dict[str, Any]:
    """Extra keyword args for ragas.evaluate(..., **kwargs)."""
    if backend == "openai":
        # Ragas uses ChatOpenAI from env by default for many versions.
        return {}

    if backend != "watsonx":
        return {}

    url = _watsonx_url()
    apikey = _watsonx_apikey()
    project_id = _watsonx_project_id()
    if not all([url, apikey, project_id]):
        raise ValueError(
            "watsonx backend requires ML URL + API key + project id "
            "(e.g. WATSONX_URL or watsonx_url; WATSONX_APIKEY or watsonx_api_key; "
            "WATSONX_PROJECT_ID or watsonx_project_id)"
        )

    # Default judge LLM; override via WATSONX_JUDGE_MODEL_ID if your catalog differs.
    model_id = os.environ.get("WATSONX_JUDGE_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")

    try:
        from ibm_watsonx_ai.foundation_models.utils.enums import EmbeddingTypes
        embed_id = os.environ.get("WATSONX_EMBED_MODEL_ID", EmbeddingTypes.IBM_SLATE_30M_ENG.value)
    except ImportError:
        embed_id = os.environ.get("WATSONX_EMBED_MODEL_ID", "ibm/slate-125m-english-rtrvr")

    try:
        from langchain_ibm import ChatWatsonx, WatsonxEmbeddings
        from ragas.llms import LangchainLLMWrapper
    except ImportError as e:
        raise ImportError(
            "watsonx Ragas backend needs: pip install -r requirements-ragas-watsonx.txt"
        ) from e

    chat = ChatWatsonx(
        model_id=model_id,
        url=url,
        api_key=apikey,
        project_id=project_id,
    )
    embeddings = WatsonxEmbeddings(
        model_id=embed_id,
        url=url,
        api_key=apikey,
        project_id=project_id,
    )
    return {
        "llm": LangchainLLMWrapper(chat),
        "embeddings": embeddings,
    }
