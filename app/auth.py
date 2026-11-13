"""One shared app password (APP_PASSWORD). A correct password gets a signed, expiring cookie; no server state,
so it works on serverless. Locally, with no APP_PASSWORD set, the app stays open on 127.0.0.1 as before."""
import hashlib
import hmac
import os
import time

COOKIE = "sprinto_session"
DAYS = 7


def required():
    return bool(os.environ.get("APP_PASSWORD")) or bool(os.environ.get("VERCEL"))


def _secret():
    return hashlib.sha256(("sprinto-session:" + os.environ["APP_PASSWORD"]).encode()).digest()


def _sign(expiry):
    return hmac.new(_secret(), str(expiry).encode(), hashlib.sha256).hexdigest()


def check_password(given):
    pw = os.environ.get("APP_PASSWORD")
    return bool(pw) and isinstance(given, str) and hmac.compare_digest(given.encode(), pw.encode())


def new_cookie(secure):
    expiry = int(time.time()) + DAYS * 86400
    return "%s=%d.%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict%s" % (
        COOKIE, expiry, _sign(expiry), DAYS * 86400, "; Secure" if secure else "")


def clear_cookie(secure):
    return "%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict%s" % (COOKIE, "; Secure" if secure else "")


def valid(cookie_header):
    """True if the request carries an unexpired cookie signed with the current password."""
    if not os.environ.get("APP_PASSWORD"):
        return False
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE and "." in value:
            expiry, sig = value.split(".", 1)
            if expiry.isdigit() and int(expiry) > time.time() and hmac.compare_digest(sig, _sign(int(expiry))):
                return True
    return False
