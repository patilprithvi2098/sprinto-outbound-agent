"""Vercel entrypoint (a WSGI `app`). Each request is replayed through the same Handler the local server uses
(app/httpd.py), so the two can never drift apart. Static screens in public/ are served by Vercel's CDN."""
import io
import os
import sys
from functools import partial

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
import httpd  # noqa: E402

_PASS_HEADERS = ("Host", "Origin", "Cookie", "Content-Type", "Content-Length", "Authorization")  # all the Handler reads


class _Connection:
    """Stands in for the socket: the request comes in as bytes, the response goes out as bytes."""

    def __init__(self, raw):
        self.inbox, self.outbox = io.BytesIO(raw), io.BytesIO()

    def makefile(self, mode, *args, **kwargs):  # the request side
        return self.inbox

    def sendall(self, data):  # the response side (socketserver writes straight to the socket)
        self.outbox.write(data)

    def settimeout(self, _):
        pass


def app(environ, start_response):
    length = environ.get("CONTENT_LENGTH") or ""
    try:  # read at most one byte past the cap, so an oversize body is still refused by the Handler
        body = environ["wsgi.input"].read(min(max(int(length), 0), httpd.MAX_BODY + 1)) if length else b""
    except ValueError:
        body = b""
    path = environ.get("PATH_INFO") or "/"
    if environ.get("QUERY_STRING"):
        path += "?" + environ["QUERY_STRING"]
    values = {"Host": environ.get("HTTP_HOST", ""), "Origin": environ.get("HTTP_ORIGIN"),
              "Cookie": environ.get("HTTP_COOKIE"), "Authorization": environ.get("HTTP_AUTHORIZATION"), "Content-Type": environ.get("CONTENT_TYPE"),
              "Content-Length": length or None}
    head = "".join("%s: %s\r\n" % (k, values[k]) for k in _PASS_HEADERS if values[k] is not None)
    raw = ("%s %s HTTP/1.1\r\n%s\r\n" % (environ["REQUEST_METHOD"], path, head)).encode("latin-1") + body
    conn = _Connection(raw)
    partial(httpd.Handler, directory=str(httpd.WEB))(conn, ("0.0.0.0", 0), None)
    response = conn.outbox.getvalue()
    top, _, payload = response.partition(b"\r\n\r\n")
    lines = top.decode("latin-1").split("\r\n")
    status = lines[0].split(" ", 1)[1]  # "HTTP/1.0 200 OK" -> "200 OK"
    headers = [tuple(x.split(": ", 1)) for x in lines[1:] if ": " in x and not x.lower().startswith(("server:", "date:"))]
    start_response(status, headers)
    return [payload]
