"""Small JSON-only provider adapter for the store assistant and agent team."""
import asyncio
import json
import logging
import re

import httpx

from backend.services.assistant_config import env_value


PROVIDERS = {"thehive", "deepseek", "gemini"}


class ProviderResponseError(ValueError):
    """Response diagnostics without storing prompts, model prose or credentials."""
    def __init__(self, reason, *, status_code=None, finish_reason=None,
                 content_characters=None, json_position=None):
        super().__init__(f"Respuesta del proveedor no utilizable: {reason}.")
        self.reason = reason
        self.status_code = status_code
        self.finish_reason = (finish_reason if isinstance(finish_reason, str)
                              and re.fullmatch(r"[A-Za-z_-]{1,40}", finish_reason) else None)
        self.content_characters = content_characters
        self.json_position = json_position


def _parse_json_object(text, *, status_code, finish_reason):
    metadata = dict(status_code=status_code, finish_reason=finish_reason,
                    content_characters=len(text) if isinstance(text, str) else None)
    if not isinstance(text, str) or not text.strip():
        raise ProviderResponseError("empty_content", **metadata)
    source = text.strip()
    # Accept a single fenced JSON document, never extract an object from prose.
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```", source, re.I)
    if fenced:
        source = fenced.group(1)

    def reject_constant(_value):
        raise ValueError("Non-standard JSON number")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result

    try:
        parsed = json.loads(source, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProviderResponseError("invalid_json", json_position=getattr(exc, "pos", None), **metadata) from exc
    if not isinstance(parsed, dict):
        raise ProviderResponseError("non_object_json", **metadata)
    return parsed


def _response_json(response):
    try:
        result = response.json()
    except ValueError as exc:
        raise ProviderResponseError("invalid_response_json", status_code=response.status_code,
                                    json_position=getattr(exc, "pos", None)) from exc
    if not isinstance(result, dict):
        raise ProviderResponseError("invalid_structure", status_code=response.status_code)
    return result


def provider_config(model_override=None):
    configured = (env_value("LLM_PROVIDER") or "thehive").strip().lower()
    provider = configured if configured in PROVIDERS else "thehive"
    if model_override:
        provider = "gemini" if model_override.startswith("gemini-") else "thehive" if model_override.startswith("deepseek-ai/") else "deepseek"
    if model_override:
        model = model_override
    elif provider == "thehive":
        model = env_value("THEHIVE_MODEL") or "deepseek-ai/deepseek-v4.1-flash-1017"
    elif provider == "deepseek":
        model = env_value("DEEPSEEK_MODEL") or "deepseek-flash"
    else:
        model = env_value("GEMINI_MODEL") or "gemini-3.1-flash-lite"
    if provider == "thehive":
        key = env_value("THEHIVE_API_KEY") or env_value("DEEPSEEK_API_KEY")
    else:
        key = env_value("DEEPSEEK_API_KEY" if provider == "deepseek" else "GEMINI_API_KEY")
    return provider, model, key


def status():
    provider, model, key = provider_config()
    fallback = (env_value("LLM_FALLBACK_PROVIDER") or "").strip().lower()
    fallback_key_name = {"thehive": "THEHIVE_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "gemini": "GEMINI_API_KEY"}.get(fallback)
    fallback_key = env_value(fallback_key_name or "") or (env_value("DEEPSEEK_API_KEY") if fallback == "thehive" else "")
    return {
        "provider": provider,
        "model": model,
        "configured": bool(key),
        "fallback_provider": fallback if fallback in PROVIDERS and fallback_key else None,
    }


async def _request(provider, model, key, instruction, context, schema):
    if not key:
        raise RuntimeError(f"No está configurada la clave del proveedor {provider}.")
    # TheHive model IDs are namespaced (vendor/model); direct provider IDs are not.
    valid_model = re.fullmatch(r"[a-zA-Z0-9._-]+", model)
    valid_hive_model = provider == "thehive" and re.fullmatch(r"[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+", model)
    if not (valid_model or valid_hive_model):
        raise ValueError("El nombre del modelo no es válido.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(22, connect=6)) as client:
        if provider in {"deepseek", "thehive"}:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": instruction + "\nDevuelve únicamente un objeto JSON válido con esta estructura: " + json.dumps(schema, ensure_ascii=False)},
                    {"role": "user", "content": context},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 1600,
            }
            endpoint = ("https://api-cdn.thehive.ai/api/v3/chat/completions" if provider == "thehive"
                        else "https://api.deepseek.com/chat/completions")
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {key}"}, json=payload,
            )
            response.raise_for_status()
            result = _response_json(response)
            try:
                choice = result["choices"][0]
                text = choice["message"].get("content")
                finish_reason = choice.get("finish_reason")
            except (KeyError, IndexError, TypeError, AttributeError) as exc:
                raise ProviderResponseError("invalid_structure", status_code=response.status_code) from exc
            if finish_reason != "stop":
                reason = "truncated" if finish_reason == "length" else "blocked" if finish_reason == "content_filter" else "unexpected_finish"
                raise ProviderResponseError(reason, status_code=response.status_code, finish_reason=finish_reason,
                                            content_characters=len(text) if isinstance(text, str) else None)
            tokens = result.get("usage", {}).get("total_tokens", 0)
        else:
            payload = {
                "systemInstruction": {"parts": [{"text": instruction}]},
                "contents": [{"role": "user", "parts": [{"text": context}]}],
                "generationConfig": {
                    "temperature": 0.1, "maxOutputTokens": 1600,
                    "responseMimeType": "application/json", "responseSchema": schema,
                },
            }
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key}, json=payload,
            )
            response.raise_for_status()
            result = _response_json(response)
            try:
                candidate = result["candidates"][0]
                finish_reason = candidate.get("finishReason")
                if finish_reason != "STOP":
                    reason = "truncated" if finish_reason == "MAX_TOKENS" else "unexpected_finish"
                    raise ProviderResponseError(reason, status_code=response.status_code, finish_reason=finish_reason)
                text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
            except (KeyError, IndexError, TypeError, AttributeError) as exc:
                raise ProviderResponseError("invalid_structure", status_code=response.status_code) from exc
            tokens = result.get("usageMetadata", {}).get("totalTokenCount", 0)
        return _parse_json_object(text, status_code=response.status_code, finish_reason=finish_reason), int(tokens or 0)


async def complete_json(instruction, context, schema, model_override=None):
    provider, model, key = provider_config(model_override)
    fallback = (env_value("LLM_FALLBACK_PROVIDER") or "").strip().lower()
    attempts = [(provider, model, key)]
    if fallback in PROVIDERS and fallback != provider:
        fallback_model_override = env_value("GEMINI_MODEL") if fallback == "gemini" else env_value("DEEPSEEK_MODEL") if fallback == "deepseek" else env_value("THEHIVE_MODEL")
        fallback_default = {"gemini": "gemini-3.1-flash-lite", "deepseek": "deepseek-flash", "thehive": "deepseek-ai/deepseek-v4.1-flash-1017"}[fallback]
        fallback_model = fallback_model_override or fallback_default
        fallback_key = (env_value("GEMINI_API_KEY") if fallback == "gemini" else env_value("DEEPSEEK_API_KEY") if fallback == "deepseek" else env_value("THEHIVE_API_KEY") or env_value("DEEPSEEK_API_KEY"))
        if fallback_key:
            attempts.append((fallback, fallback_model, fallback_key))
    last_error = None
    for index, (candidate, candidate_model, candidate_key) in enumerate(attempts):
        try:
            parsed, tokens = await _request(candidate, candidate_model, candidate_key, instruction, context, schema)
            return parsed, candidate, candidate_model, tokens
        except (httpx.HTTPError, asyncio.TimeoutError, ValueError, KeyError, IndexError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else getattr(exc, "status_code", None)
            logging.getLogger(__name__).warning(
                "Proveedor LLM %s falló: %s HTTP=%s reason=%s finish=%s chars=%s json_pos=%s",
                candidate, type(exc).__name__, status_code, getattr(exc, "reason", None),
                getattr(exc, "finish_reason", None), getattr(exc, "content_characters", None),
                getattr(exc, "json_position", None))
            last_error = exc
            if index + 1 < len(attempts):
                continue
    raise RuntimeError("Ningún proveedor LLM disponible devolvió JSON válido.") from last_error
