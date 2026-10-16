"""Live connectivity check for the OpenAI provider used by core.llm.

Skipped automatically when OPENAI_API_KEY is not configured (for example in CI).
"""
import json
import os

import pytest

openai = pytest.importorskip("openai")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-5-nano")

pytestmark = pytest.mark.skipif(not api_key, reason="OPENAI_API_KEY not configured; skipping live API test.")


def test_openai_api_returns_requested_json():
    client = openai.OpenAI(api_key=api_key, timeout=60.0, max_retries=2)
    response = client.responses.create(
        model=model,
        instructions=(
            "You are an API connection tester. "
            "Return only a valid JSON object with keys "
            '"status" and "answer". Set status to "ok" '
            "and answer to 2."
        ),
        input="Return the requested JSON object.",
        text={"format": {"type": "json_object"}},
    )
    content = response.output_text
    assert content, "The model returned an empty response."
    result = json.loads(content)
    assert result.get("status") == "ok", result
    assert result.get("answer") == 2, result
