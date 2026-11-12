"""Security fixes from the Phase 6 audit, checked against a real server on a spare loopback port."""
import http.client
import json
import os
import socket
import sys
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import runs  # noqa: E402
import scrape  # noqa: E402
import server  # noqa: E402

GOOD = "127.0.0.1:8321"  # the Host the browser sends for the real app; the test server listens elsewhere


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._latest = runs.latest
        runs.latest = lambda: None  # never read real run records from a test
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.Handler, directory=str(server.WEB)))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        runs.latest = cls._latest

    def request(self, method, path, host=GOOD, origin=None, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host)
        if origin:
            conn.putheader("Origin", origin)
        data = json.dumps(body).encode() if body is not None else b""
        for k, v in (headers or {"Content-Type": "application/json", "Content-Length": str(len(data))}).items():
            conn.putheader(k, v)
        conn.endheaders()
        if data:
            conn.send(data)
        res = conn.getresponse()
        out = (res.status, dict(res.getheaders()), res.read())
        conn.close()
        return out

    def test_foreign_host_is_refused_for_api_and_pages(self):
        self.assertEqual(self.request("GET", "/api/runs/latest", host="attacker.example:8321")[0], 421)
        self.assertEqual(self.request("GET", "/review.html", host="attacker.example:8321")[0], 421)
        self.assertEqual(self.request("POST", "/api/domains", host="attacker.example:8321", body={"text": "a.io"})[0], 421)

    def test_app_hosts_still_work(self):
        self.assertEqual(self.request("GET", "/api/runs/latest")[0], 200)
        self.assertEqual(self.request("GET", "/api/runs/latest", host="localhost:8321")[0], 200)
        status, _, body = self.request("POST", "/api/domains", origin="http://127.0.0.1:8321", body={"text": "kestrelmetrics.io"})
        self.assertEqual((status, json.loads(body)["valid"]), (200, ["kestrelmetrics.io"]))

    def test_foreign_origin_is_refused(self):
        self.assertEqual(self.request("POST", "/api/domains", origin="https://attacker.example", body={"text": "a.io"})[0], 403)
        self.assertEqual(self.request("GET", "/api/runs/latest", origin="null")[0], 403)

    def test_negative_length_is_refused_without_reading(self):
        status, _, _ = self.request("POST", "/api/domains", headers={"Content-Type": "application/json", "Content-Length": "-1"})
        self.assertEqual(status, 400)

    def test_pages_cannot_be_framed(self):
        _, headers, _ = self.request("GET", "/review.html")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Content-Security-Policy"), "frame-ancestors 'none'")
        self.assertEqual(self.request("GET", "/api/runs/latest")[1].get("X-Frame-Options"), "DENY")

    def test_stalled_body_releases_the_thread(self):
        old = server.Handler.timeout
        server.Handler.timeout = 0.5
        self.addCleanup(setattr, server.Handler, "timeout", old)
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(b"POST /api/domains HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{\"te"
                  % GOOD.encode())
        s.settimeout(5)
        self.assertEqual(s.recv(1024), b"")  # the server closes the connection instead of waiting forever
        s.close()


class ChromeEnvironment(unittest.TestCase):
    def test_chrome_gets_no_secrets(self):
        seen = {}
        old_run, old_exists = scrape.subprocess.run, scrape.os.path.exists
        scrape.subprocess.run = lambda args, **kw: seen.update(kw) or type("R", (), {"stdout": b""})()
        scrape.os.path.exists = lambda p: True
        self.addCleanup(setattr, scrape.subprocess, "run", old_run)
        self.addCleanup(setattr, scrape.os.path, "exists", old_exists)
        os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "sk-test-dummy")
        scrape.render("https://kestrelmetrics.io/")
        self.assertEqual(set(seen["env"]), {"PATH", "HOME"})
        self.assertNotIn("sk-", json.dumps(seen["env"]))


class RunIdShape(unittest.TestCase):
    def test_trailing_newline_is_refused(self):
        self.assertEqual(runs.act("20261112-130000\n", "dub.co", "send")[1][0], 400)


if __name__ == "__main__":
    unittest.main()
