"""
LLM provider setup for the AU-Ggregates AI agent.

Supports two backends:
- Groq cloud API (primary, if GROQ_API_KEY is set)
- Local Ollama (fallback)
"""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

load_dotenv()


def _resolve_ollama_base_url() -> str:
    """Resolve the Ollama base URL from environment variables.

    Priority:
    1. OLLAMA_BASE_URL
    2. OLLAMA_URL with '/api/generate' stripped
    3. Default: http://localhost:11434
    """
    base_url = os.getenv("OLLAMA_BASE_URL")
    if base_url:
        return base_url.rstrip("/")

    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        return ollama_url.replace("/api/generate", "").rstrip("/")

    return "http://localhost:11434"


def create_llm():
    """Create and return the LLM instance.

    Uses Groq if GROQ_API_KEY is set, otherwise falls back to local Ollama.

    Returns:
        A LangChain chat model (ChatGroq or ChatOllama).

    Raises:
        ConnectionError: If using Ollama and the server is unreachable.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")

    if groq_api_key:
        model = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
        llm = ChatGroq(api_key=groq_api_key, model=model, temperature=0.1)
        print(f"  ✅ Using Groq API (model: {model})")
        return llm

    # Fallback to local Ollama
    base_url = _resolve_ollama_base_url()
    model = os.getenv("OLLAMA_MODEL", "qwen3:4b")

    from httpx import Timeout

    llm = ChatOllama(
        base_url=base_url,
        model=model,
        temperature=0.1,
        num_ctx=16384,
        num_predict=4096,
        keep_alive="10m",
        disable_streaming=True,
        client_kwargs={"timeout": Timeout(timeout=300.0)},
    )

    # Verify Ollama is reachable
    import urllib.request
    try:
        print("  ⏳ Checking Ollama connection...")
        urllib.request.urlopen(f"{base_url}/api/tags", timeout=5)
        print(f"  ✅ Using Ollama (model: {model})")
    except Exception as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {base_url}. "
            "Please make sure Ollama is running (ollama serve)."
        ) from exc

    return llm
