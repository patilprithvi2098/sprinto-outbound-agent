"""Claude Messages API over urllib (the project is stdlib-only on Python 3.9; the SDK needs 3.10+)."""
import json
import os
import urllib.error
import urllib.request

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"


class ClaudeError(Exception):
    pass


def ask_json(model, system, user, schema, effort="medium", timeout=180):
    """One call constrained to `schema` (output_config.format); returns the parsed object."""
    body = {
        "model": model,
        "max_tokens": 16000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    headers = {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    if model == SONNET:  # refusal on Sonnet 5.5 retries on a fallback model inside the same call
        body["fallbacks"] = "default"
        headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
    request = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            message = json.load(response)
    except urllib.error.HTTPError as e:
        raise ClaudeError("The Claude API answered HTTP %d." % e.code)
    except Exception as e:
        raise ClaudeError("Could not reach the Claude API (%s)." % type(e).__name__)
    if message.get("stop_reason") == "refusal":
        raise ClaudeError("The model declined this request.")
    if message.get("stop_reason") == "max_tokens":
        raise ClaudeError("The model ran out of room before finishing.")
    text = next((b["text"] for b in message.get("content", []) if b.get("type") == "text"), "")
    try:
        return json.loads(text)
    except ValueError:
        raise ClaudeError("The model did not return valid JSON.")
