"""Every failure from the architecture check, triggered on purpose."""
import io
import json
import smtplib
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
import claude  # noqa: E402
import mailer  # noqa: E402
import metrics  # noqa: E402
import pipeline  # noqa: E402
import scrape  # noqa: E402
from test_phase1 import BASE  # noqa: E402


def http_error(code):
    return urllib.error.HTTPError("https://example.invalid", code, "x", {}, io.BytesIO(b""))


class Swap:
    """Replace attributes for one test and put them back afterwards."""

    def __init__(self, test):
        self.test = test

    def __call__(self, obj, name, value):
        old = getattr(obj, name)
        self.test.addCleanup(setattr, obj, name, old)
        setattr(obj, name, value)


class ClaudeFailures(unittest.TestCase):
    def setUp(self):
        self.swap = Swap(self)
        self.swap(claude, "BACKOFF", 0)
        self.calls = 0

    def answers(self, *outcomes):
        outcomes = list(outcomes)

        def urlopen(request, timeout=None):
            self.calls += 1
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return io.BytesIO(json.dumps(out).encode())
        self.swap(claude.urllib.request, "urlopen", urlopen)

    OK = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "{\"a\": 1}"}],
          "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}}

    def test_timeout_is_retried_three_times_then_reported(self):
        self.answers(socket.timeout(), socket.timeout(), socket.timeout())
        with self.assertRaises(claude.ClaudeError) as e:
            claude.ask_json(claude.HAIKU, "s", "u", {})
        self.assertEqual(self.calls, 3)
        self.assertIn("3 tries", str(e.exception))

    def test_overload_then_success(self):
        self.answers(http_error(529), http_error(429), self.OK)
        before = claude.spent["usd"]
        self.assertEqual(claude.ask_json(claude.HAIKU, "s", "u", {}), {"a": 1})
        self.assertEqual(self.calls, 3)
        self.assertAlmostEqual(claude.spent["usd"] - before, 0.10 + 0.05)  # 1M in at $0.10, 0.1M out at $0.50

    def test_bad_key_or_model_aborts_at_once(self):
        for code in (401, 404):
            self.calls = 0
            self.answers(http_error(code))
            with self.assertRaises(claude.ClaudeError):
                claude.ask_json(claude.HAIKU, "s", "u", {})
            self.assertEqual(self.calls, 1)


class PageFailures(unittest.TestCase):
    def setUp(self):
        self.swap = Swap(self)
        self.swap(scrape, "RETRY_WAIT", 0)
        self.swap(scrape, "assert_public", lambda host: None)
        self.swap(scrape, "_robots_allow", lambda url: True)
        self.opens = 0

    def site(self, *outcomes):
        outcomes = list(outcomes)
        test = self

        class Response(io.BytesIO):
            class headers:
                get_content_charset = staticmethod(lambda: "utf-8")

        class Opener:
            def open(self, request, timeout=None):
                test.opens += 1
                out = outcomes.pop(0)
                if isinstance(out, Exception):
                    raise out
                return Response(out.encode())
        self.swap(scrape.urllib.request, "build_opener", lambda *a: Opener())

    def test_timeout_is_retried_then_flagged(self):
        self.site(socket.timeout(), socket.timeout(), socket.timeout())
        page = scrape.fetch("https://kestrelmetrics.io/")
        self.assertEqual((page["ok"], self.opens), (False, 3))
        self.assertIn("after 3 tries", page["reason"])

    def test_a_block_is_never_retried(self):
        self.site(http_error(403))
        page = scrape.fetch("https://kestrelmetrics.io/")
        self.assertEqual(self.opens, 1)
        self.assertIn("blocked automated access", page["reason"])

    def test_empty_page_gets_one_browser_try_then_a_flag(self):
        renders = []
        self.swap(scrape, "render", lambda url: renders.append(url) or "<p>still nothing</p>")
        self.site("<html><body><div id=root></div></body></html>")
        page = scrape.fetch("https://kestrelmetrics.io/")
        self.assertEqual((page["ok"], len(renders)), (False, 1))
        self.assertIn("site needs a browser", page["reason"])

    def test_browser_try_can_rescue_the_page(self):
        self.swap(scrape, "render", lambda url: "<p>%s</p>" % " ".join("word%d" % i for i in range(300)))
        self.site("<html><body><div id=root></div></body></html>")
        self.assertTrue(scrape.fetch("https://kestrelmetrics.io/")["ok"])


class GmailFailures(unittest.TestCase):
    def setUp(self):
        self.swap = Swap(self)
        self.swap(mailer, "RETRY_WAIT", 0)
        for key in ("OPERATOR_EMAIL", "GMAIL_APP_PASSWORD"):
            self.swap(mailer.os, "environ", dict(mailer.os.environ, OPERATOR_EMAIL="op@example.com",
                                                 GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"))
        self.tries = 0

    def smtp(self, *outcomes):
        outcomes = list(outcomes)
        test = self

        class Fake:
            def __init__(self, *a, **k):
                test.tries += 1
                out = outcomes.pop(0)
                if out:
                    raise out

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def login(self, *a):
                pass

            def send_message(self, m):
                test.to = m["To"]
        self.swap(mailer.smtplib, "SMTP_SSL", Fake)

    def test_one_retry_then_success(self):
        self.smtp(smtplib.SMTPServerDisconnected(), None)
        mailer.send_to_operator("s", "b")
        self.assertEqual((self.tries, self.to), (2, "op@example.com"))

    def test_two_failures_are_reported(self):
        self.smtp(smtplib.SMTPServerDisconnected(), smtplib.SMTPServerDisconnected())
        with self.assertRaises(smtplib.SMTPServerDisconnected):
            mailer.send_to_operator("s", "b")
        self.assertEqual(self.tries, 2)

    def test_rejected_login_is_not_retried(self):
        self.smtp(smtplib.SMTPAuthenticationError(535, b"bad"))
        with self.assertRaises(smtplib.SMTPAuthenticationError):
            mailer.send_to_operator("s", "b")
        self.assertEqual(self.tries, 1)


FIELDS = dict(BASE, company_name="Kestrel Metrics", what_it_does="Usage analytics for product teams",
              trigger="opened a Frankfurt region", trigger_quote="Now live in Frankfurt")
FOUND = {"ok": True, "fields": FIELDS, "evidence": [], "pages": [], "extra_fetches_used": 0, "stop": "all fields filled"}


class RunLevelStops(unittest.TestCase):
    def setUp(self):
        self.swap = Swap(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.swap(pipeline, "DATA", Path(self.tmp.name))
        self.swap(pipeline, "ROOT", Path(self.tmp.name))
        self.swap(pipeline, "research", lambda domain: dict(FOUND, fields=dict(FIELDS)))
        self.swap(pipeline, "HUNTER_WAIT", 0)

    def test_hunter_bad_key_stops_hunter_for_the_rest_of_the_run(self):
        calls = []

        def hunter(domain):
            calls.append(domain)
            raise pipeline.HunterStop("Hunter rejected the key (HTTP 401).")
        self.swap(pipeline, "hunter_people", hunter)
        halt = {}
        a = pipeline.run_company("a.io", "r", halt=halt)
        b = pipeline.run_company("b.io", "r", halt=halt)
        self.assertEqual(calls, ["a.io"])
        for r in (a, b):
            self.assertEqual(r["verdict"], "flagged")
            self.assertIn("Hunter rejected the key", r["reason"])

    def test_quota_exhausted_and_401_and_timeouts_inside_hunter(self):
        self.swap(pipeline.os, "environ", dict(pipeline.os.environ, HUNTER_API_KEY="k"))
        self.swap(pipeline.checks, "check_hunter", lambda: {"ok": True, "searches_left": 0, "searches_total": 50})
        with self.assertRaises(pipeline.HunterStop):
            pipeline.hunter_people("a.io")
        self.swap(pipeline.checks, "check_hunter", lambda: {"ok": True, "searches_left": 9, "searches_total": 50})
        tries = []

        def get_json(url, timeout=10):
            tries.append(1)
            raise socket.timeout()
        self.swap(pipeline.checks, "get_json", get_json)
        with self.assertRaises(RuntimeError) as e:
            pipeline.hunter_people("a.io")
        self.assertNotIsInstance(e.exception, pipeline.HunterStop)  # a timeout flags one company, not the run
        self.assertEqual(len(tries), 3)
        self.assertNotIn("api_key", str(e.exception))

        def refused(url, timeout=10):
            raise http_error(401)
        self.swap(pipeline.checks, "get_json", refused)
        with self.assertRaises(pipeline.HunterStop):
            pipeline.hunter_people("a.io")

    def test_cost_cap_stops_research_for_the_rest_of_the_run(self):
        researched = []
        self.swap(pipeline, "research", lambda d: researched.append(d) or {"ok": False, "reason": "blocked", "pages": []})
        halt = {}
        pipeline.run_company("a.io", "r", halt=halt)
        self.swap(claude, "spent", {"usd": claude.spent["usd"] + pipeline.CONFIG["max_run_cost_usd"]})
        r = pipeline.run_company("b.io", "r", halt=halt)
        self.assertEqual(researched, ["a.io"])
        self.assertIn("cost cap", r["reason"])

    def test_claude_failure_flags_the_company_and_never_guesses(self):
        def broken(domain):
            raise claude.ClaudeError("Could not reach the Claude API (timeout) on 3 tries.")
        self.swap(pipeline, "research", broken)
        r = pipeline.run_company("a.io", "r")
        self.assertEqual((r["verdict"], r["rule_applied"]), ("flagged", "extraction failed"))
        self.assertNotIn("draft", r)


class KillCriteria(unittest.TestCase):
    def test_rates_and_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            now = datetime.now(timezone.utc)  # judgements are stamped with the real clock
            run = data / "runs" / "20261110-090000"
            run.mkdir(parents=True)
            domains = ["a.io", "b.io", "c.io", "d.io"]
            (run / "run.json").write_text(json.dumps({
                "started_at": (now - timedelta(days=2)).isoformat(),
                "finished_at": (now - timedelta(days=2) + timedelta(minutes=4)).isoformat(), "domains": domains}))
            reviews = [{"sent_at": "t"}, {"sent_at": "t", "rewritten": True}, {"skipped": True}, {}]
            for d, review in zip(domains, reviews):
                (run / ("%s.json" % d)).write_text(json.dumps(
                    {"domain": d, "verdict": "qualified", "review": review, "claude_cost_usd": 0.05}))
            old = data / "runs" / "20261001-090000"  # outside the week: ignored
            old.mkdir()
            (old / "run.json").write_text(json.dumps({"started_at": (now - timedelta(days=40)).isoformat(),
                                                      "finished_at": None, "domains": ["z.io"]}))
            out, _ = metrics.report(data, now)
            self.assertEqual((out["rewrite_rate"], out["minutes_per_company"], out["claude_cost_usd"]), (0.67, 1.0, 0.2))
            self.assertEqual(out["kill"], ["rewrites or skips over 50%"])
            self.assertEqual(out["to_check"], domains)
            self.assertIsNone(out["false_qualify_rate"])

            for d, verdict in (("a.io", "ok"), ("b.io", "false_qualify"), ("c.io", "wrong_contact"),
                               ("d.io", "wrong_contact"), ("d.io", "ok")):  # the later judgement on d.io wins
                metrics.judge(d, verdict, data)
            out, _ = metrics.report(data)
            self.assertEqual((out["false_qualify_rate"], out["contact_accuracy"], out["to_check"]), (0.25, 0.75, []))


if __name__ == "__main__":
    unittest.main()
