"""Setup check: prove the three credentials work without spending anything."""
import json
import os
import smtplib
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_UA = {"User-Agent": "sprinto-outbound-agent/0.1"}


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip("\"'")


def get_json(url, headers=None, timeout=10):
    request = urllib.request.Request(url, headers=dict(_UA, **(headers or {})))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _result(ok, detail, **extra):
    return dict(ok=ok, detail=detail, **extra)


def _http_check(name, call):
    # Error text never includes the URL: Hunter's key travels in the query string.
    try:
        return call()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return _result(False, "%s rejected the key (HTTP %d)." % (name, e.code))
        return _result(False, "%s answered HTTP %d." % (name, e.code))
    except Exception as e:
        return _result(False, "Could not reach %s (%s)." % (name, type(e).__name__))


def check_claude():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _result(False, "Not set. Add ANTHROPIC_API_KEY to .env.")

    def call():
        get_json("https://api.anthropic.com/v1/models?limit=1",
                 {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return _result(True, "Key accepted.")
    return _http_check("The Claude API", call)


def check_hunter():
    key = os.environ.get("HUNTER_API_KEY")
    if not key:
        return _result(False, "Not set. Add HUNTER_API_KEY to .env.")

    def call():
        searches = get_json("https://api.hunter.io/v2/account?api_key=" + key)["data"]["requests"]["searches"]
        return _result(True, "Key accepted.", searches_left=searches["available"] - searches["used"],
                       searches_total=searches["available"])
    return _http_check("Hunter", call)


def check_gmail():
    recipient, password = os.environ.get("OPERATOR_EMAIL"), os.environ.get("GMAIL_APP_PASSWORD")
    sender = os.environ.get("GMAIL_SENDER") or recipient  # the account that logs in; mail still goes only to OPERATOR_EMAIL
    if not recipient or not password:
        return _result(False, "Not set. Add OPERATOR_EMAIL and GMAIL_APP_PASSWORD to .env.")
    if "@" not in sender or " " in sender:  # Gmail just drops the connection on a malformed login name
        return _result(False, "GMAIL_SENDER is not an email address. Put your full Gmail address there.")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(sender, password.replace(" ", ""))  # Google shows app passwords in groups of four
        return _result(True, "Login accepted as %s. Emails will go to %s only." % (sender, recipient))
    except smtplib.SMTPAuthenticationError:
        return _result(False, "Gmail rejected the login. Use an app password, not your normal password.")
    except Exception as e:
        return _result(False, "Could not reach Gmail (%s)." % type(e).__name__)


def run_all():
    load_env()
    return {"claude": check_claude(), "hunter": check_hunter(), "gmail": check_gmail()}
