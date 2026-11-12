import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import runs  # noqa: E402

RID = "20261112-140000"
READY = {"domain": "kestrelmetrics.io", "name": "Kestrel Metrics", "verdict": "qualified", "reason": "fits",
         "flags": [], "evidence": [{"field": "trigger", "quote": "Frankfurt region", "page_url": "https://kestrelmetrics.io/"}],
         "fields": {"trigger_quote": "Frankfurt region"}, "record_path": "x",
         "contact": {"name": "Ines Albrecht", "first_name": "Ines", "position": "Head of Security", "email": "i@k.io",
                     "confidence": 91, "verification_status": "valid", "why_this_person": "tier 1"},
         "draft": {"subject": "Frankfurt", "hook": "H.", "pain": "P.", "value": "V.", "ask": "A?", "grader_verdict": "ready",
                   "model": "m", "counts": {"from_pack": 4, "generic": 0, "made_up": 0, "banned": 0},
                   "pains": [{"pain": "a", "evidence_field": "f"}, {"pain": "b", "evidence_field": "g"}],
                   "role_measured_on": "r"}}


class Actions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        runs.RUNS = Path(self.tmp.name)
        d = runs.RUNS / RID
        d.mkdir()
        (d / "run.json").write_text(json.dumps({"id": RID, "started_at": "t", "finished_at": "t",
                                                "domains": ["kestrelmetrics.io", "fernpay.com"]}))
        (d / "kestrelmetrics.io.json").write_text(json.dumps(READY))
        (d / "fernpay.com.json").write_text(json.dumps({"domain": "fernpay.com", "verdict": "disqualified", "reason": "SOC 2"}))
        self.sent = []
        runs.send_to_operator = lambda subject, body: self.sent.append((subject, body))

    def tearDown(self):
        self.tmp.cleanup()

    def test_send_twice_emails_once(self):
        r, err = runs.act(RID, "kestrelmetrics.io", "send")
        self.assertIsNone(err)
        self.assertEqual(r["status"], "Sent to me")
        runs.act(RID, "kestrelmetrics.io", "send")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("DRAFT ONLY", self.sent[0][1])

    def test_rewrote_then_send_stays_rewritten(self):
        runs.act(RID, "kestrelmetrics.io", "rewrote")
        r, _ = runs.act(RID, "kestrelmetrics.io", "send")
        self.assertEqual(r["status"], "Rewritten")

    def test_no_action_on_a_dropped_company(self):
        self.assertEqual(runs.act(RID, "fernpay.com", "send")[1][0], 409)
        self.assertEqual(self.sent, [])

    def test_bad_input_is_refused_before_touching_files(self):
        self.assertEqual(runs.act("../../etc", "kestrelmetrics.io", "send")[1][0], 400)
        self.assertEqual(runs.act(RID, "../run", "send")[1][0], 404)
        self.assertEqual(runs.act(RID, "kestrelmetrics.io", "delete")[1][0], 400)

    def test_failed_send_is_recorded_and_can_be_retried(self):
        def boom(subject, body):
            raise OSError("down")
        runs.send_to_operator = boom
        self.assertEqual(runs.act(RID, "kestrelmetrics.io", "send")[1][0], 502)
        runs.send_to_operator = lambda s, b: self.sent.append(s)
        self.assertEqual(runs.act(RID, "kestrelmetrics.io", "send")[0]["status"], "Sent to me")

    def test_state_marks_unfinished_companies(self):
        meta = json.loads((runs.RUNS / RID / "run.json").read_text())
        meta.update(domains=meta["domains"] + ["tallybook.co"], finished_at=None)
        (runs.RUNS / RID / "run.json").write_text(json.dumps(meta))
        s = runs.state(RID)
        self.assertEqual([r["status"] for r in s["records"]], ["Qualified", "Disqualified", "Researching"])
        self.assertTrue(s["interrupted"])  # no thread is running it


if __name__ == "__main__":
    unittest.main()
