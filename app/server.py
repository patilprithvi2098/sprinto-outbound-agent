"""Local server for the Sprinto outbound agent. Run: python3 app/server.py"""
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import checks
from domains import parse_domains

WEB = Path(__file__).resolve().parent.parent / "web"
HOST, PORT = "127.0.0.1", 8321  # loopback only: this app holds credentials
MAX_BODY = 20_000


class Handler(SimpleHTTPRequestHandler):
    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/setup-check":
            return self._json(200, checks.run_all())
        if self.path.startswith("/api/"):
            return self._json(404, {"error": "Not found."})
        super().do_GET()

    def do_POST(self):
        # JSON only: another website cannot send this content type here without a preflight we never answer.
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._json(415, {"error": "Send JSON."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "Bad request."})
        if length > MAX_BODY:
            return self._json(413, {"error": "That list is too long. Paste at most 15 domains."})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "Bad request."})
        if self.path == "/api/domains" and isinstance(data, dict) and isinstance(data.get("text"), str):
            return self._json(200, parse_domains(data["text"]))
        self._json(404, {"error": "Not found."})


if __name__ == "__main__":
    checks.load_env()
    print("Sprinto outbound agent on http://%s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), partial(Handler, directory=str(WEB))).serve_forever()
