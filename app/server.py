"""Local server for the Sprinto outbound agent. Run: python3 app/server.py"""
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import checks
import feedback
import runs
from domains import parse_domains

WEB = Path(__file__).resolve().parent.parent / "web"
HOST, PORT = "127.0.0.1", 8321  # loopback only: this app holds credentials
MAX_BODY = 20_000
# DNS rebinding: a hostile page can point its own hostname at 127.0.0.1 and become "same origin" with this
# server, so every request must name this server itself in Host, and a browser Origin, when sent, must match.
ALLOWED_HOSTS = {"%s:%d" % (HOST, PORT), "localhost:%d" % PORT}
ALLOWED_ORIGINS = {"http://" + h for h in ALLOWED_HOSTS}


class Handler(SimpleHTTPRequestHandler):
    timeout = 10  # a client that stalls mid-request releases its thread instead of holding it forever

    def _trusted(self):
        origin = self.headers.get("Origin")
        if self.headers.get("Host", "").lower() in ALLOWED_HOSTS and (origin is None or origin.lower() in ALLOWED_ORIGINS):
            return True
        self._json(421 if self.headers.get("Host", "").lower() not in ALLOWED_HOSTS else 403,
                   {"error": "Open the app at http://%s:%d." % (HOST, PORT)})
        return False

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if not self.path.startswith("/api/"):  # API replies set their own header
            self.send_header("Cache-Control", "no-cache")  # always recheck pages and scripts, so the browser never runs an old screen
        self.send_header("X-Frame-Options", "DENY")  # no other site may frame the Send and Skip buttons
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        super().end_headers()

    def do_GET(self):
        if not self._trusted():
            return
        if self.path == "/api/setup-check":
            return self._json(200, dict(checks.run_all(), estimate={"cost_per_company": runs.cost_per_company()}))
        if self.path == "/api/quota":  # Hunter only: the Review screen should not log in to Gmail on every load
            return self._json(200, checks.check_hunter())
        if self.path == "/api/feedback":
            return self._json(200, dict(feedback.status(), **runs.loop_summary()))
        if self.path == "/api/runs/latest":
            return self._json(200, {"run": runs.latest()})
        if self.path.startswith("/api/"):
            return self._json(404, {"error": "Not found."})
        super().do_GET()

    def do_POST(self):
        if not self._trusted():
            return
        # JSON only: another website cannot send this content type here without a preflight we never answer.
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._json(415, {"error": "Send JSON."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "Bad request."})
        if length < 0:  # a negative length would make read() take everything until the client hangs up
            return self._json(400, {"error": "Bad request."})
        if length > MAX_BODY:
            return self._json(413, {"error": "That list is too long. Paste at most 15 domains."})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "Bad request."})
        if not isinstance(data, dict):
            return self._json(400, {"error": "Bad request."})
        if self.path == "/api/domains" and isinstance(data.get("text"), str):
            return self._json(200, parse_domains(data["text"]))
        if self.path == "/api/run" and isinstance(data.get("text"), str):
            parsed = parse_domains(data["text"])
            if not parsed["valid"]:
                return self._json(400, {"error": "No valid domains to run.", "rejected": parsed["rejected"]})
            run_id, error = runs.start(parsed["valid"])
            if error:
                return self._json(409, {"error": error})
            return self._json(202, {"run_id": run_id, "domains": parsed["valid"], "rejected": parsed["rejected"]})
        if self.path == "/api/action" and all(isinstance(data.get(k), str) for k in ("run_id", "domain", "action")):
            edits = {k: data[k] for k in ("subject", "body", "reason") if k in data}
            limits = {"subject": feedback.MAX_SUBJECT, "body": feedback.MAX_BODY, "reason": feedback.MAX_REASON}
            if any(not isinstance(v, str) or len(v) > limits[k] for k, v in edits.items()):
                return self._json(400, {"error": "That text is too long. Shorten it and try again."})
            record, error = runs.act(data["run_id"], data["domain"], data["action"], edits)  # the recipient is never taken from the request
            if error:
                return self._json(error[0], {"error": error[1]})
            return self._json(200, {"record": record})
        self._json(404, {"error": "Not found."})


if __name__ == "__main__":
    checks.load_env()
    print("Sprinto outbound agent on http://%s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), partial(Handler, directory=str(WEB))).serve_forever()
