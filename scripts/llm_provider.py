"""
llm_provider.py

A thin abstraction so generate_post.py doesn't care which AI provider is
active. Switch providers by setting LLM_PROVIDER to "anthropic", "openai",
or "gemini" (as a GitHub repo secret/variable, or in your local .env).

Each provider function takes the same inputs (system prompt, user prompt,
max tokens) and returns the same thing: a plain text string of the model's
reply. generate_post.py then parses that text the same way regardless of
which provider produced it.

Model choice per provider is set via env vars too, with sensible defaults,
so upgrading to a newer model later is a one-line config change, not a
code change.
"""

import os
import requests

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower().strip()

# Default model per provider. Override with the matching env var if you want
# a different model without touching code.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.5",
    "gemini": "gemini-3.5-flash",
}


def _get_model() -> str:
    env_key = f"{PROVIDER.upper()}_MODEL"
    return os.environ.get(env_key, DEFAULT_MODELS.get(PROVIDER, ""))


def _call_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": _get_model(),
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(block["text"] for block in data["content"] if block["type"] == "text")


def _call_openai(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _get_model(),
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"].get("content")
    if not content or not str(content).strip():
        finish_reason = data["choices"][0].get("finish_reason", "unknown")
        raise RuntimeError(
            f"OpenAI returned empty content (finish_reason={finish_reason}). "
            "Try a higher max_tokens limit or a different model."
        )
    return content


def _call_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    model = _get_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise RuntimeError("Gemini returned empty content. Try a higher max_tokens limit.")
    return text


_PROVIDER_FUNCS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
}


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    """
    Calls whichever provider is active (LLM_PROVIDER env var) and returns
    the plain text reply. Raises a clear error if the provider name is
    unrecognized or its API key is missing, rather than failing silently.
    """
    func = _PROVIDER_FUNCS.get(PROVIDER)
    if func is None:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{PROVIDER}'. Must be one of: {list(_PROVIDER_FUNCS)}"
        )
    return func(system_prompt, user_prompt, max_tokens)


def active_provider_label() -> str:
    return f"{PROVIDER} ({_get_model()})"
