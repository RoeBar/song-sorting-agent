import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_DEFAULT_MODEL = "google/gemini-2.5-flash"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _api_key() -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    return key


def _client() -> OpenAI:
    base = (os.environ.get("OPENROUTER_BASE_URL") or _DEFAULT_BASE_URL).strip()
    return OpenAI(base_url=base, api_key=_api_key())


def chat_json(system_instruction: str, user_message: str) -> str:
    """Call OpenRouter with JSON-shaped output (OpenAI-compatible chat completions)."""
    model = (os.environ.get("OPENROUTER_MODEL") or _DEFAULT_MODEL).strip()
    client = _client()
    extra_headers = {}
    referer = (os.environ.get("OPENROUTER_HTTP_REFERER") or "").strip()
    if referer:
        extra_headers["HTTP-Referer"] = referer
    title = (os.environ.get("OPENROUTER_APP_TITLE") or "song-sorting-agent").strip()
    if title:
        extra_headers["X-Title"] = title

    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    if extra_headers:
        kwargs["extra_headers"] = extra_headers

    completion = client.chat.completions.create(**kwargs)
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("Model returned an empty response.")
    return text
