"""Fetch one public page and reduce it to readable text."""
import ipaddress
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urlparse

USER_AGENT = "OutboundResearchBot/0.1 (single page fetch)"
MAX_BYTES = 2_000_000
THIN_PAGE_WORDS = 200
# Footers stay in: certification badges ("SOC 2 Type II") usually live there.
_SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "nav"}


ATTEMPTS, RETRY_WAIT = 3, 1.0
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render(url):
    """The page as headless Chrome sees it, in a throwaway profile. Returns "" if Chrome is missing or fails.
    shortcut: Chrome's own redirects are not re-checked against private addresses, pin the resolved IP if this ever runs beyond one trusted user"""
    if not os.path.exists(CHROME):
        return ""
    with tempfile.TemporaryDirectory() as profile:
        try:
            out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--mute-audio",
                                  "--user-data-dir=" + profile, "--user-agent=" + USER_AGENT,
                                  "--virtual-time-budget=8000", "--dump-dom", url],
                                 capture_output=True, timeout=45,
                                 env={"PATH": "/usr/bin:/bin", "HOME": profile})  # the site's page runs here: no keys in its environment
            return out.stdout.decode("utf-8", errors="replace")[:MAX_BYTES]
        except Exception:
            return ""


class Blocked(Exception):
    pass


def assert_public(host):
    # shortcut: checks the address at lookup time only, upgrade to pinning the resolved IP if this ever runs beyond one trusted user
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise Blocked("The domain does not resolve.")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise Blocked("The domain points at a private address.")


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_public(urlparse(newurl).hostname or "")
        return super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302  # Python 3.9 does not follow 308


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(" ".join(data.split()))


def clean(html):
    parser = _Text()
    parser.feed(html)
    return "\n".join(dict.fromkeys(parser.parts))  # drops repeated lines, keeps order


def _robots_allow(url):
    parts = urlparse(url)
    # Fetched with our own user agent: RobotFileParser.read() uses Python's default one, and sites
    # that block it answer 403, which the parser then reads as "everything is forbidden".
    request = urllib.request.Request("%s://%s/robots.txt" % (parts.scheme, parts.netloc),
                                     headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.build_opener(_RedirectGuard).open(request, timeout=10) as response:
            lines = response.read(500_000).decode("utf-8", errors="replace").splitlines()
    except Exception:
        return True  # no readable robots.txt means no published rule; a blocked site fails at the page fetch
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(lines)
    return robots.can_fetch(USER_AGENT, url)


def fetch(url):
    """Return {ok, reason, text, words}. Never raises: a failed page is a result, not a crash."""
    def fail(reason):
        return {"ok": False, "reason": reason, "text": "", "words": 0}

    try:
        assert_public(urlparse(url).hostname or "")
        if not _robots_allow(url):
            return fail("robots.txt disallows automated access")
        opener = urllib.request.build_opener(_RedirectGuard)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(1, ATTEMPTS + 1):
            try:
                with opener.open(request, timeout=15) as response:
                    raw = response.read(MAX_BYTES)
                    charset = response.headers.get_content_charset() or "utf-8"
                break
            except (Blocked, urllib.error.HTTPError):
                raise  # an answer, even a refusal, is not retried
            except Exception:
                if attempt == ATTEMPTS:
                    raise
                time.sleep(RETRY_WAIT * attempt)
    except Blocked as e:
        return fail(str(e))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429, 503):
            return fail("site blocked automated access (HTTP %d)" % e.code)
        return fail("page not available (HTTP %d)" % e.code)
    except Exception as e:  # timeouts, TLS and connection errors
        return fail("could not reach the site after %d tries (%s)" % (ATTEMPTS, type(e).__name__))

    text = clean(raw.decode(charset, errors="replace"))
    words = len(text.split())
    if words < THIN_PAGE_WORDS:  # built by JavaScript: try a real browser once
        text = clean(render(url))
        words = len(text.split())
        if words < THIN_PAGE_WORDS:
            return {"ok": False, "reason": "site needs a browser: the page arrived nearly empty (%d words) even "
                    "in headless Chrome" % words, "text": text, "words": words}
    return {"ok": True, "reason": "", "text": text, "words": words}
