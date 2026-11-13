"""Claude Messages API over urllib (the project is stdlib-only on Python 3.9; the SDK needs 3.10+)."""
import json
import os
import time
import urllib.error
import urllib.request

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
PRICES = {HAIKU: (0.10, 0.50), SONNET: (2.00, 10.00)}  # dollars per million tokens: input, output
RETRYABLE = {408, 429, 500, 502, 503, 504, 529}  # 400/401/403/404 never get better by waiting
ATTEMPTS, BACKOFF = 3, 2.0
spent = {"usd": 0.0}  # running total for this process; the pipeline reads it for the per-run cost cap


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class ClaudeError(Exception):
    pass


def ask_json(model, system, user, schema, effort="medium", timeout=120):
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
    opener = urllib.request.build_opener(_NoRedirect)  # the key never follows a redirect
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                message = json.load(response)
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE:
                raise ClaudeError("The Claude API refused the request (HTTP %d). Check the key and model." % e.code)
            failure = "The Claude API was busy (HTTP %d) on %d tries." % (e.code, ATTEMPTS)
        except Exception as e:  # timeouts and connection errors
            failure = "Could not reach the Claude API (%s) on %d tries." % (type(e).__name__, ATTEMPTS)
        if attempt == ATTEMPTS:
            raise ClaudeError(failure)
        time.sleep(BACKOFF * 2 ** (attempt - 1))
    usage, price = message.get("usage") or {}, PRICES.get(model, PRICES[SONNET])
    spent["usd"] += (usage.get("input_tokens", 0) * price[0] + usage.get("output_tokens", 0) * price[1]) / 1e6
    if message.get("stop_reason") == "refusal":
        raise ClaudeError("The model declined this request.")
    if message.get("stop_reason") == "max_tokens":
        raise ClaudeError("The model ran out of room before finishing.")
    text = next((b["text"] for b in message.get("content", []) if b.get("type") == "text"), "")
    try:
        return json.loads(text)
    except ValueError:
        raise ClaudeError("The model did not return valid JSON.")
