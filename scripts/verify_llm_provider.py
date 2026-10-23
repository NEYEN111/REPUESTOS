"""Focused provider response checks; no API calls, credentials or store writes."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services import llm_provider as provider


class ProviderResponseChecks(unittest.IsolatedAsyncioTestCase):
    async def request(self, payload, name="thehive", raw=False):
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, content=payload if raw else json.dumps(payload).encode(), request=request))
        original = httpx.AsyncClient
        with patch.object(provider.httpx, "AsyncClient", side_effect=lambda **kwargs: original(transport=transport)):
            return await provider._request(name, "vendor/model" if name == "thehive" else "gemini-test",
                                           "test-credential", "Devuelve un plan.", "Consulta de prueba", {})

    def response(self, content, finish="stop"):
        return {"choices": [{"finish_reason": finish, "message": {"content": content}}],
                "usage": {"total_tokens": 12}}

    async def test_accepts_complete_object_and_single_json_fence(self):
        for source in ['{"intent":"search"}', '```json\n{"intent":"search"}\n```']:
            with self.subTest(source=source):
                result, tokens = await self.request(self.response(source))
                self.assertEqual(result, {"intent": "search"})
                self.assertEqual(tokens, 12)

    async def test_rejects_partial_mixed_or_ambiguous_content(self):
        for source, reason in [
            ('{"intent":', "invalid_json"), ('Prosa {"intent":"search"}', "invalid_json"),
            ('{"intent":"search"}\nTexto', "invalid_json"), ('[]', "non_object_json"),
            ('null', "non_object_json"), ('{"a":NaN}', "invalid_json"),
            ('{"a":1,"a":2}', "invalid_json"), ('', "empty_content"), (None, "empty_content"),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(provider.ProviderResponseError) as caught:
                    await self.request(self.response(source))
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(caught.exception.status_code, 200)

    async def test_rejects_nonfinal_response_even_when_json_is_valid(self):
        for finish, reason in [('length', 'truncated'), ('content_filter', 'blocked'), (None, 'unexpected_finish')]:
            with self.subTest(finish=finish):
                with self.assertRaises(provider.ProviderResponseError) as caught:
                    await self.request(self.response('{"intent":"search"}', finish))
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(caught.exception.status_code, 200)

    async def test_distinguishes_invalid_http_body_from_model_content(self):
        for payload, raw, reason in [(b"not-json", True, "invalid_response_json"), ({"choices": []}, False, "invalid_structure")]:
            with self.subTest(reason=reason):
                with self.assertRaises(provider.ProviderResponseError) as caught:
                    await self.request(payload, raw=raw)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(caught.exception.status_code, 200)

    async def test_gemini_preserves_thought_separation_and_completion_check(self):
        candidate = {"finishReason": "STOP", "content": {"parts": [
            {"text": "private-internal-text", "thought": True}, {"text": '{"intent":"search"}'}]}}
        result, _ = await self.request({"candidates": [candidate]}, name="gemini")
        self.assertEqual(result, {"intent": "search"})
        candidate["finishReason"] = "MAX_TOKENS"
        with self.assertRaises(provider.ProviderResponseError) as caught:
            await self.request({"candidates": [candidate]}, name="gemini")
        self.assertEqual(caught.exception.reason, "truncated")

    async def test_error_log_contains_metadata_without_credential_or_content(self):
        error = provider.ProviderResponseError("invalid_json", status_code=200, finish_reason="stop",
                                               content_characters=17, json_position=16)
        with patch.object(provider, "provider_config", return_value=("thehive", "vendor/model", "test-credential")), \
                patch.object(provider, "env_value", return_value=""), \
                patch.object(provider, "_request", side_effect=error), \
                self.assertLogs(provider.__name__, level="WARNING") as logs:
            with self.assertRaises(RuntimeError):
                await provider.complete_json("private-prompt", "private-content", {})
        text = " ".join(logs.output)
        self.assertIn("HTTP=200", text)
        self.assertIn("reason=invalid_json", text)
        self.assertIn("finish=stop", text)
        self.assertIn("json_pos=16", text)
        for value in ["test-credential", "private-prompt", "private-content"]:
            self.assertNotIn(value, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
