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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):  # calls that carry an API key must not follow a redirect to another host
        return None


def get_json(url, headers=None, timeout=10):
    request = urllib.request.Request(url, headers=dict(_UA, **(headers or {})))
    with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
        return json.load(response)


class _PlainText:
    """Terminal output filter: text from websites, Hunter or the model could hide control codes; drop them."""

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        return self.stream.write("".join(c for c in text if c in "\n\t" or (c.isprintable() and not 0x80 <= ord(c) < 0xA0)))

    def flush(self):
        self.stream.flush()


def plain_terminal():
    import sys
    sys.stdout = _PlainText(sys.stdout)


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
    except smtplib.SMTPServerDisconnected:  # Gmail often hangs up on a bad login instead of answering it
        return _result(False, "Gmail closed the connection during login. The address or the app password is "
                              "probably wrong.")
    except Exception as e:
        return _result(False, "Could not reach Gmail (%s)." % type(e).__name__)


def check_storage():
    import store  # imported here: store picks files or Neon when it loads
    if isinstance(store.STORE, store.FileStore):
        return _result(True, "Saved in files on this computer.")
    try:
        store.STORE.records()
        saved = len(store.STORE.run_ids())
    except ImportError:
        return _result(False, "The database driver is missing. Install requirements.txt.")
    except Exception as e:  # the type only: a driver message can carry the connection string
        if not os.environ.get("DATABASE_URL"):
            return _result(False, "Not set. Add DATABASE_URL in the Vercel project settings.")
        import traceback
        last = traceback.extract_tb(e.__traceback__)[-1]  # where it failed: a file name and line, no values
        where = "%s:%d" % (os.path.basename(last.filename), last.lineno)
        note = " %s" % e if isinstance(e, AttributeError) else ""  # names an attribute, never a credential
        return _result(False, "Could not use the database (%s at %s%s). Check DATABASE_URL and that db/schema.sql was run."
                       % (type(e).__name__, where, note))
    from urllib.parse import urlparse
    host = (urlparse(os.environ.get("DATABASE_URL") or "").hostname or "").split(".")[0]  # which database, no login details
    return _result(True, "Connected to %s. %d %s saved." % (host, saved, "run" if saved == 1 else "runs"))


def run_all():
    load_env()
    return {"claude": check_claude(), "hunter": check_hunter(), "gmail": check_gmail(), "storage": check_storage()}
