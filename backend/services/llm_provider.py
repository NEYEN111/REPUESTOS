"""Small JSON-only provider adapter for the store assistant and agent team."""
import asyncio
import json
import logging
import re

import httpx

from backend.services.assistant_config import env_value


PROVIDERS = {"thehive", "deepseek", "gemini"}


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
            result = response.json()
            text = result["choices"][0]["message"]["content"]
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
            result = response.json()
            candidate = result["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("Respuesta incompleta del proveedor.")
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
            tokens = result.get("usageMetadata", {}).get("totalTokenCount", 0)
        return json.loads(text), int(tokens or 0)


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
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            logging.getLogger(__name__).warning("Proveedor LLM %s falló: %s HTTP=%s", candidate, type(exc).__name__, status_code)
            last_error = exc
            if index + 1 < len(attempts):
                continue
    raise RuntimeError("Ningún proveedor LLM disponible devolvió JSON válido.") from last_error
