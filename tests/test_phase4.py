import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import checks  # noqa: E402
import feedback  # noqa: E402
import pipeline  # noqa: E402
import runs  # noqa: E402
from test_phase3 import READY, RID  # noqa: E402

DRAFT = {"subject": "Frankfurt region and security reviews", "hook": "Kestrel opened a Frankfurt region.",
         "pain": "EU buyers will ask for ISO 27001.", "value": "Sprinto automates ISO 27001 for SaaS companies.",
         "ask": "Is ISO 27001 on your plan?"}
BODY = "Hi Ines,\n\n%(hook)s %(pain)s\n\n%(value)s\n\n%(ask)s\n" % DRAFT


class Compare(unittest.TestCase):
    def test_untouched_draft_is_no_signal(self):
        self.assertIsNone(feedback.compare(DRAFT, DRAFT["subject"], BODY))
        self.assertIsNone(feedback.compare(DRAFT, DRAFT["subject"] + " ", BODY.replace("\n\n", "\n \n") + "\n"))

    def test_names_exactly_the_parts_that_changed(self):
        edited = BODY.replace(DRAFT["ask"], "Worth a quick reply?")
        c = feedback.compare(DRAFT, DRAFT["subject"], edited)
        self.assertEqual(c["changed_parts"], ["ask"])
        self.assertTrue(0 < c["disagreement"] < 0.5)
        c = feedback.compare(DRAFT, "Frankfurt", BODY.replace(DRAFT["hook"], "Saw the Frankfurt launch."))
        self.assertEqual(c["changed_parts"], ["subject", "hook"])
        c = feedback.compare(DRAFT, DRAFT["subject"], BODY.replace(DRAFT["pain"], "That means audits."))
        self.assertEqual(c["changed_parts"], ["pain"])

    def test_merged_paragraphs_fall_back_to_body(self):
        c = feedback.compare(DRAFT, DRAFT["subject"], "Hi Ines,\n\nOne short paragraph instead.\n")
        self.assertEqual(c["changed_parts"], ["body"])

    def test_greeting_is_never_stored(self):
        c = feedback.compare(DRAFT, DRAFT["subject"], BODY.replace(DRAFT["ask"], "Reply?"))
        self.assertNotIn("Ines", c["body_after"])
        row = feedback.row_for(dict(READY, draft=dict(READY["draft"], **DRAFT)), c, "  too long  ")
        self.assertNotIn("Ines", json.dumps(row))
        self.assertNotIn("@", json.dumps(row))
        self.assertEqual(row["reason"], "too long")


class Apply(unittest.TestCase):
    def test_pattern_needs_a_repeat(self):
        self.assertEqual(feedback.pattern_line([["hook"], ["ask"]]), "")
        self.assertEqual(feedback.pattern_line([["hook", "ask"], ["hook"], ["value"]]),
                         "He rewrote the hook in 2 of his last 3 edits.")

    def test_corrections_reach_the_writer_as_data(self):
        found = {"rows": [{"id": 7, "contact_role": "CTO", "company_stage": None, "subject_before": "A",
                           "body_before": "long", "subject_after": "B", "body_after": "short", "reason": "too long"}],
                 "pattern": "He rewrote the ask in 2 of his last 2 edits.", "error": None}
        seen = {}
        original = pipeline.ask_json
        pipeline.ask_json = lambda model, system, user, schema, effort="medium": seen.update(user=user) or {}
        try:
            pipeline.write_draft({"company": "Kestrel"}, "m", feedback.prompt_section(found))
        finally:
            pipeline.ask_json = original
        self.assertIn("<corrections>", seen["user"])
        self.assertIn("AFTER body: short", seen["user"])
        self.assertIn("His reason: too long", seen["user"])
        self.assertEqual(feedback.prompt_section({"rows": [], "pattern": "", "error": None}), "")

    def test_database_down_never_raises(self):
        old = os.environ.pop("DATABASE_URL", None)
        try:
            self.assertEqual(feedback.retrieve(1, None)["rows"], [])
            self.assertIsNone(feedback.store({})[0])
            self.assertFalse(feedback.status()["ok"])
        finally:
            if old:
                os.environ["DATABASE_URL"] = old


class Capture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        runs.RUNS = Path(self.tmp.name)
        d = runs.RUNS / RID
        d.mkdir()
        (d / "run.json").write_text(json.dumps({"id": RID, "started_at": "t", "finished_at": "t",
                                                "domains": ["kestrelmetrics.io"]}))
        (d / "kestrelmetrics.io.json").write_text(json.dumps(dict(READY, draft=dict(READY["draft"], **DRAFT))))
        self.sent, self.rows = [], []
        runs.send_to_operator = lambda subject, body: self.sent.append((subject, body))
        self._store = feedback.store
        feedback.store = lambda row: (self.rows.append(row) or len(self.rows), None)

    def tearDown(self):
        feedback.store = self._store
        self.tmp.cleanup()

    def act(self, action, **edits):
        return runs.act(RID, "kestrelmetrics.io", action, edits)

    def test_untouched_send_stores_nothing(self):
        r, _ = self.act("send", subject=DRAFT["subject"], body=BODY, reason="")
        self.assertEqual((r["status"], self.rows, r["review"]["disagreement"]), ("Sent to me", [], 0.0))

    def test_edited_send_stores_exactly_one_row_and_sends_the_edit(self):
        edited = BODY.replace(DRAFT["ask"], "Worth a one-line reply?")
        r, _ = self.act("send", subject=DRAFT["subject"], body=edited, reason="softer ask")
        self.act("send", subject=DRAFT["subject"], body=edited)  # double click
        self.assertEqual(r["status"], "Rewritten")
        self.assertEqual(len(self.rows), 1)
        self.assertEqual((self.rows[0]["changed_parts"], self.rows[0]["reason"], self.rows[0]["rejected"]),
                         (["ask"], "softer ask", False))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Worth a one-line reply?", self.sent[0][1])
        self.assertTrue(r["review"]["correction"]["saved"])

    def test_skip_stores_one_rejection(self):
        self.act("skip", reason="wrong person")
        self.act("skip")
        self.assertEqual(len(self.rows), 1)
        self.assertEqual((self.rows[0]["rejected"], self.rows[0]["disagreement"], self.rows[0]["body_after"]),
                         (True, 1.0, ""))

    def test_empty_edit_is_refused_and_nothing_is_sent(self):
        self.assertEqual(self.act("send", subject="", body=BODY)[1][0], 400)
        self.assertEqual(self.sent, [])

    def test_save_failure_does_not_block_the_send(self):
        feedback.store = lambda row: (None, "the feedback database could not be reached (TimeoutError)")
        r, err = self.act("send", subject="New subject", body=BODY)
        self.assertIsNone(err)
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(r["review"]["correction"]["saved"])

    def test_average_and_kill_rule(self):
        self.act("skip")
        self.assertEqual(runs.loop_summary(), {"drafts_counted": 1, "avg_disagreement": 1.0})
        self.assertTrue(runs._mostly_rejected(runs.state(RID)))


@unittest.skipUnless(os.environ.get("NEON_CHECK"), "set NEON_CHECK=1 to run against the real database (rolled back)")
class Neon(unittest.TestCase):
    def test_insert_and_retrieve_inside_a_rolled_back_transaction(self):
        checks.load_env()
        change = feedback.compare(DRAFT, DRAFT["subject"], BODY.replace(DRAFT["ask"], "Worth a one-line reply?"))
        row = feedback.row_for(dict(READY, draft=dict(READY["draft"], **DRAFT)), change, "softer ask")
        row["operator"] = "selftest-rolled-back"
        row["role_tier"] = 1
        conn = feedback._connect()
        try:
            row_id = feedback._insert(conn, row)
            rows, parts = feedback._select(conn, "selftest-rolled-back", 1, None)
            self.assertEqual([r["id"] for r in rows], [row_id])
            self.assertEqual(rows[0]["body_after"], change["body_after"])
            self.assertEqual(parts, [["ask"]])
        finally:
            conn.rollback()  # nothing is left behind
            conn.close()
        self.assertTrue(feedback.status()["ok"])


if __name__ == "__main__":
    unittest.main()
