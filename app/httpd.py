"""Local server for the Sprinto outbound agent. Run: python3 app/httpd.py
(Not named server.py: Vercel would take app/server.py as the app entrypoint; the entrypoint is wsgi.py at the top.)"""
import json
import os
import socket
import time
import traceback
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import auth
import checks
import discover
import feedback
import runs
from domains import parse_domains

WEB = Path(__file__).resolve().parent.parent / "public"  # public/: Vercel serves it straight from its CDN
HOST, PORT = "127.0.0.1", 8321  # loopback only: this app holds credentials
MAX_BODY = 20_000
# DNS rebinding: a hostile page can point its own hostname at 127.0.0.1 and become "same origin" with this
# server, so every request must name this server itself in Host, and a browser Origin, when sent, must match.
ALLOWED_HOSTS = {"%s:%d" % (HOST, PORT), "localhost:%d" % PORT}
ALLOWED_ORIGINS = {"http://" + h for h in ALLOWED_HOSTS}
ON_VERCEL = bool(os.environ.get("VERCEL"))  # public HTTPS host: rebinding does not apply, the Origin must match the Host
OPEN_ROUTES = {"/api/login", "/api/logout", "/api/cron", "/api/work"}  # the timer and the research chain bring CRON_SECRET instead of the cookie


def store_has_run(run_id):
    return bool(runs.store.STORE.get("run", run_id))


class Handler(SimpleHTTPRequestHandler):
    timeout = 10  # a client that stalls mid-request releases its thread instead of holding it forever

    def _trusted(self):
        host, origin = self.headers.get("Host", "").lower(), self.headers.get("Origin")
        if ON_VERCEL:
            if origin is None or origin.lower() == "https://" + host:
                return True
            self._json(403, {"error": "Requests must come from this app."})
            return False
        if host in ALLOWED_HOSTS and (origin is None or origin.lower() in ALLOWED_ORIGINS):
            return True
        self._json(421 if host not in ALLOWED_HOSTS else 403, {"error": "Open the app at http://%s:%d." % (HOST, PORT)})
        return False

    def _signed_in(self):
        """API calls need the app password's cookie whenever a password is set (always on Vercel)."""
        if not self.path.startswith("/api/") or self.path in OPEN_ROUTES or not auth.required():
            return True
        if not os.environ.get("APP_PASSWORD"):
            # names only, never values: says which Vercel environment this is and catches a misspelt name
            near = [k for k in os.environ if k != "APP_PASSWORD" and k.strip().upper().replace("-", "_") == "APP_PASSWORD"]
            self._json(503, {"error": "The app password is not set. Add APP_PASSWORD in the Vercel project settings.",
                             "environment": os.environ.get("VERCEL_ENV"), "similar_names": near,
                             "set_but_empty": "APP_PASSWORD" in os.environ})
            return False
        if auth.valid(self.headers.get("Cookie")):
            return True
        self._json(401, {"error": "Sign in with the app password.", "login": True})
        return False

    def _json(self, code, payload, cookie=None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        if cookie:
            self.send_header("Set-Cookie", cookie)
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

    def _safely(self, work):
        """An unexpected failure is answered in words, so the screen never has to say the app is not responding."""
        try:
            work()
        except (socket.timeout, ConnectionError):  # the client stalled or left: nobody to answer
            raise
        except Exception as e:
            traceback.print_exc()  # full detail in the server log only
            storage = checks.check_storage()
            why = "Storage: " + storage["detail"] if not storage["ok"] else "The app hit an error (%s). Try again." % type(e).__name__
            self._json(500, {"error": why})

    def do_GET(self):
        self._safely(self._get)

    def do_POST(self):
        self._safely(self._post)

    def _get(self):
        if not self._trusted() or not self._signed_in():
            return
        if self.path == "/api/cron":  # Vercel's daily timer: find companies and research them, no one signed in
            if not discover.cron_allowed(self.headers.get("Authorization")):
                return self._json(401, {"error": "Not allowed."})
            return self._json(200, discover.daily(self.headers.get("Host")))
        if self.path == "/api/quota":  # Hunter only: the Review screen should not log in to Gmail on every load
            return self._json(200, checks.check_hunter())
        if self.path == "/api/feedback":
            return self._json(200, dict(feedback.status(), **runs.loop_summary()))
        if self.path == "/api/runs/latest":
            return self._json(200, {"run": runs.latest()})
        if self.path.startswith("/api/"):
            return self._json(404, {"error": "Not found."})
        super().do_GET()

    def _post(self):
        if not self._trusted() or not self._signed_in():
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
        if self.path == "/api/login":
            if auth.check_password(data.get("password")):
                return self._json(200, {"ok": True}, cookie=auth.new_cookie(secure=ON_VERCEL))
            time.sleep(1)  # slows password guessing
            return self._json(401, {"error": "That password is not right."})
        if self.path == "/api/logout":
            return self._json(200, {"ok": True}, cookie=auth.clear_cookie(secure=ON_VERCEL))
        if self.path == "/api/setup-check":  # POST only: it logs in to Gmail, so a stray link or image must not trigger it
            result = checks.run_all()  # the estimate reads the database, so it is skipped when storage is down
            cost = runs.cost_per_company() if result["storage"]["ok"] else None
            return self._json(200, dict(result, estimate={"cost_per_company": cost}))
        if self.path == "/api/step" and isinstance(data.get("run_id"), str):
            state, error = runs.step(data["run_id"])
            if error:
                return self._json(error[0], {"error": error[1]})
            return self._json(200, {"run": state})
        if self.path == "/api/work":  # one hop of the server-side research chain (discover.kick)
            if not discover.cron_allowed(self.headers.get("Authorization")):
                return self._json(401, {"error": "Not allowed."})
            if not isinstance(data.get("run_id"), str) or not runs.RUN_ID.fullmatch(data["run_id"]) or not store_has_run(data["run_id"]):
                return self._json(400, {"error": "Bad request."})
            return self._json(200, discover.work(data["run_id"], self.headers.get("Host")))
        if self.path == "/api/discover":  # the operator's "Find companies now"
            try:
                run_id, domains, error = discover.start_found()
            except RuntimeError as e:
                return self._json(502, {"error": str(e)})
            if error:
                return self._json(409, {"error": error})
            return self._json(202, {"run_id": run_id, "domains": domains, "background": discover.kick(run_id, self.headers.get("Host"))})
        if self.path == "/api/domains" and isinstance(data.get("text"), str):
            return self._json(200, parse_domains(data["text"]))
        if self.path == "/api/run" and isinstance(data.get("text"), str):
            parsed = parse_domains(data["text"])
            if not parsed["valid"]:
                return self._json(400, {"error": "No valid domains to run.", "rejected": parsed["rejected"]})
            run_id, error = runs.start(parsed["valid"])
            if error:
                return self._json(409, {"error": error})
            discover.kick(run_id, self.headers.get("Host"))
            return self._json(202, {"run_id": run_id, "domains": parsed["valid"], "rejected": parsed["rejected"]})
        if self.path == "/api/action" and all(isinstance(data.get(k), str) for k in ("run_id", "domain", "action")):
            edits = {k: data[k] for k in ("subject", "body", "reason", "note", "person") if k in data}
            limits = {"subject": feedback.MAX_SUBJECT, "body": feedback.MAX_BODY, "reason": feedback.MAX_REASON,
                      "note": feedback.MAX_REASON, "person": 320}
            if any(not isinstance(v, str) or len(v) > limits[k] for k, v in edits.items()):
                return self._json(400, {"error": "That text is too long. Shorten it and try again."})
            if "cc" in data:  # a list of addresses; runs.act only accepts people Hunter found at this company
                if not isinstance(data["cc"], list) or any(not isinstance(e, str) for e in data["cc"]):
                    return self._json(400, {"error": "Bad request."})
                edits["cc"] = data["cc"]
            record, error = runs.act(data["run_id"], data["domain"], data["action"], edits)  # the recipient is never taken from the request
            if error:
                return self._json(error[0], {"error": error[1]})
            return self._json(200, {"record": record})
        self._json(404, {"error": "Not found."})


if __name__ == "__main__":
    checks.load_env()
    print("Sprinto outbound agent on http://%s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), partial(Handler, directory=str(WEB))).serve_forever()
