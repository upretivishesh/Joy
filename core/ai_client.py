import json
import re
from typing import Any, Optional

RECOMMENDED_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def _infer_provider(model: str) -> str:
    return "anthropic" if (model or "").strip().lower().startswith("claude") else "openai"


def _extract_json_payload(raw: str) -> str:
    text = re.sub(r"```json|```", "", raw or "", flags=re.IGNORECASE).strip()

    try:
        json.loads(text)
        return text
    except Exception:
        pass

    obj_match = re.search(r"\{[\s\S]*\}", text)
    arr_match = re.search(r"\[[\s\S]*\]", text)

    candidates = []
    if obj_match:
        candidates.append(obj_match.group(0))
    if arr_match:
        candidates.append(arr_match.group(0))

    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            continue

    raise ValueError(f"Model did not return valid JSON: {text[:300]}")


def chat_json(
    system: str,
    user: str,
    api_key: str,
    model: str,
    max_tokens: int = 500,
    temperature: float = 0,
    provider: Optional[str] = None,
) -> Any:
    provider = provider or _infer_provider(model)
    raw = _chat_raw(system, user, api_key, model, max_tokens, temperature, provider)
    cleaned = _extract_json_payload(raw)
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
    return "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
