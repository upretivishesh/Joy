"""
core/ai_client.py — one call surface for Joy's AI calls, regardless of
whether they end up hitting OpenAI or Anthropic.

WHY THIS EXISTS
Joy's AI calls are almost all the same shape: "read this text, judge it,
return strict JSON" — resume scoring, industry classification, keyword
extraction, name extraction. That's exactly the kind of short, structured,
high-volume call Claude Haiku is priced and built for. Rather than branch
provider-specific SDK code into scoring.py and llm_extractor.py directly,
every call site goes through chat_json()/chat_text() here, and this file
is the only place that needs to know OpenAI's and Anthropic's SDKs differ.

PROVIDER SELECTION
Pass provider="openai" or provider="anthropic" explicitly, or leave it as
None and it's inferred from the model string — anything starting with
"claude" routes to Anthropic, everything else routes to OpenAI. This means
existing call sites that pass api_key/model through unchanged don't need
to know or care which provider they're hitting.

COST NOTE (checked July 2026, verify against current pricing before
relying on this for a client pitch — rates change):
  gpt-4o-mini            $0.15 / $0.60 per million tokens (in/out)
  claude-haiku-4-5       $1.00 / $5.00 per million tokens
  gpt-4o                 $2.50 / $10.00 per million tokens
  claude-sonnet-5        $2.00 / $10.00 (intro, through Aug 31 2026)
On raw per-token price, gpt-4o-mini is cheaper than Claude Haiku. Claude
only comes out ahead here if the comparison is against full gpt-4o, or if
Haiku's output needs fewer retries/corrections in practice than 4o-mini
does on your specific prompts — that's worth testing on real Joy data
before deciding, not assuming from the rate card alone.
"""

import json
import re
from typing import Any, Optional

RECOMMENDED_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def _infer_provider(model: str) -> str:
    return "anthropic" if (model or "").strip().lower().startswith("claude") else "openai"


def chat_json(
    system: str,
    user: str,
    api_key: str,
    model: str,
    max_tokens: int = 500,
    temperature: float = 0,
    provider: Optional[str] = None,
) -> Any:
    """
    Sends a system+user prompt, expects JSON back (object or array — both
    are valid json.loads() results), returns it parsed.

    Raises on failure (bad JSON, network error, auth error) rather than
    swallowing it — every existing call site already wraps AI calls in its
    own try/except and builds a specific fallback (heuristic score, empty
    list, etc.), so silently returning None here would just push the same
    handling one level down with less context about what broke.
    """
    provider = provider or _infer_provider(model)
    raw = _chat_raw(system, user, api_key, model, max_tokens, temperature, provider)
    cleaned = re.sub(r"```json|```", "", raw or "").strip()
    return json.loads(cleaned)


def chat_text(
    system: str,
    user: str,
    api_key: str,
    model: str,
    max_tokens: int = 500,
    temperature: float = 0,
    provider: Optional[str] = None,
) -> str:
    """Same as chat_json but returns raw text, for prompts that don't ask
    for JSON back."""
    provider = provider or _infer_provider(model)
    return (_chat_raw(system, user, api_key, model, max_tokens, temperature, provider) or "").strip()


def _chat_raw(system: str, user: str, api_key: str, model: str, max_tokens: int, temperature: float, provider: str) -> str:
    if provider == "anthropic":
        return _call_anthropic(system, user, api_key, model, max_tokens, temperature)
    return _call_openai(system, user, api_key, model, max_tokens, temperature)


def _call_openai(system: str, user: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=25,
    )
    return response.choices[0].message.content or ""


def _call_anthropic(system: str, user: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        timeout=25,
    )
    # content is a list of blocks (text, tool_use, ...) — join the text ones.
    return "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )