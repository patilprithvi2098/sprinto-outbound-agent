import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from pipeline import check_draft, pick_contact, qualify, research  # noqa: E402
from test_phase1 import BASE, person  # noqa: E402

EMPTY = dict(BASE, b2b_saas="unknown", b2b_saas_quote="", stage="unknown", stage_quote="",
             funding_round="unknown", funding_round_quote="")


def fake_site(pages):
    """pages: {path: fields dict or None for a 404}. Records which paths were fetched."""
    fetched = []

    def get(domain, path):
        fetched.append(path)
        if pages.get(path) is None:
            return {"ok": False, "reason": "page not available (HTTP 404)", "text": ""}
        return {"ok": True, "reason": "", "text": path}

    return get, (lambda text, url: dict(pages[text])), fetched


class Loop(unittest.TestCase):
    def test_fills_missing_fields_from_the_right_pages(self):
        get, read, fetched = fake_site({
            "/": dict(EMPTY, b2b_saas="yes", b2b_saas_quote="API for finance teams"),
            "/security": dict(EMPTY, certified="no", certified_quote="SOC 2 in progress", certified_in_progress=True),
            "/careers": dict(EMPTY, stage="hiring 12 roles", stage_quote="12 open roles",
                             trigger="opened a London office", trigger_quote="We just opened in London")})
        out = research("acme.io", get, read)
        self.assertEqual(out["stop"], "all fields filled")
        self.assertEqual(fetched, ["/", "/security", "/careers"])
        self.assertEqual(out["fields"]["stage"], "hiring 12 roles")
        self.assertEqual({e["field"] for e in out["evidence"]} >= {"b2b_saas", "certified", "stage", "trigger"}, True)

    def test_stops_at_the_cap_and_404s_count(self):
        get, read, fetched = fake_site({"/": dict(EMPTY, b2b_saas="yes", b2b_saas_quote="SaaS for HR teams")})
        out = research("acme.io", get, read)
        self.assertEqual(out["extra_fetches_used"], 4)
        self.assertEqual(len(fetched), 5)
        self.assertTrue(out["stop"].startswith("cap reached"))

    def test_a_404_moves_to_the_next_page_for_the_same_field(self):
        get, read, fetched = fake_site({
            "/": dict(EMPTY, b2b_saas="yes", b2b_saas_quote="SaaS for HR teams", stage="Series B",
                      stage_quote="our Series B", trigger="new EU region", trigger_quote="Now live in the EU"),
            "/trust": dict(EMPTY, certified="yes", certified_quote="SOC 2 Type II")})
        out = research("acme.io", get, read)
        self.assertEqual(fetched, ["/", "/security", "/trust"])
        self.assertEqual(out["fields"]["certified"], "yes")

    def test_certification_stops_the_loop_at_once(self):
        get, read, fetched = fake_site({"/": dict(EMPTY, certified="yes", certified_quote="SOC 2 Type II")})
        out = research("acme.io", get, read)
        self.assertEqual(fetched, ["/"])
        self.assertEqual(qualify(out["fields"])[1], "already certified")

    def test_blocked_homepage_is_a_result_not_a_crash(self):
        get = lambda d, p: {"ok": False, "reason": "site blocked automated access (HTTP 403)", "text": ""}  # noqa: E731
        out = research("acme.io", get, None)
        self.assertFalse(out["ok"])
        self.assertIn("blocked", out["reason"])


class CertBackstop(unittest.TestCase):
    def test_held_versus_not_held(self):
        from pipeline import CERT_HELD, CERT_PENDING
        held = lambda q: bool(CERT_HELD.search(q)) and not CERT_PENDING.search(q)  # noqa: E731
        self.assertTrue(held("Clerk is SOC 2 type 2 compliant and CCPA compliant."))
        self.assertTrue(held("Linear has achieved ISO/IEC 27001:2022 certification"))
        self.assertFalse(held("Are you SOC 2 or ISO 27001 certified? Not yet."))  # savvycal.com, a real lead
        self.assertFalse(held("SOC 2 Type II audit in progress"))
        self.assertFalse(held("We help you get SOC 2 fast"))


class TooSmall(unittest.TestCase):
    def test_pre_seed_is_dropped(self):
        f = dict(BASE, funding_round="pre-seed", funding_round_quote="our pre-seed round")
        self.assertEqual(qualify(f)[1], "too small or too early")

    def test_small_team_is_dropped_unless_it_sells_to_enterprises(self):
        f = dict(BASE, team_size=8, team_size_quote="a team of 8")
        self.assertEqual(qualify(f)[1], "too small or too early")
        f.update(enterprise_signal=True, enterprise_signal_quote="Enterprise plan")
        verdict, _, _, flags = qualify(f)
        self.assertEqual(verdict, "qualified")
        self.assertTrue(any("small team" in x for x in flags))

    def test_cap_reached_is_flagged(self):
        self.assertTrue(any("cap reached" in x for x in qualify(BASE, "cap reached (4 extra pages) with stage")[3]))


class LargeCompany(unittest.TestCase):
    def test_large_company_needs_a_security_owner(self):
        people = [person("CTO", 95), person("CEO", 99)]
        self.assertIsNone(pick_contact(people, require_tier1=True)[0])
        self.assertEqual(pick_contact(people + [person("Head of GRC", 80, first="G")], True)[0]["first_name"], "G")


DRAFT = {"subject": "Your London office", "hook": "Congrats on opening in London.",
         "pain": "New regions bring new security reviews.", "value": "Sprinto automates SOC 2 for SaaS companies.",
         "ask": "Is SOC 2 on your list this year?"}
ALL_FROM_PACK = {n: {"label": "FROM PACK", "pack_field": "facts.trigger", "note": ""} for n in range(1, 5)}


class Grade(unittest.TestCase):
    def test_clean_draft_is_ready(self):
        trace, counts, verdict, problems = check_draft(DRAFT, ALL_FROM_PACK)
        self.assertEqual((verdict, counts["from_pack"], len(trace)), ("ready", 4, 4))

    def test_banned_word_is_caught_in_code_even_if_the_grader_missed_it(self):
        d = dict(DRAFT, value="Sprinto helps you streamline SOC 2.")
        trace, counts, verdict, problems = check_draft(d, ALL_FROM_PACK)
        self.assertEqual((verdict, counts["banned"]), ("flagged", 1))

    def test_made_up_or_skipped_sentence_flags(self):
        labels = dict(ALL_FROM_PACK)
        del labels[2]
        self.assertEqual(check_draft(DRAFT, labels)[2], "flagged")

    def test_too_generic_flags(self):
        labels = {n: {"label": "GENERIC", "pack_field": "", "note": ""} for n in range(1, 3)}
        labels.update({n: ALL_FROM_PACK[n] for n in range(3, 5)})
        self.assertIn("too generic (2 of 4 sentences)", check_draft(DRAFT, labels)[3])

    def test_em_dash_flags(self):
        self.assertIn("em dash", check_draft(dict(DRAFT, hook="London — nice."), ALL_FROM_PACK)[3])


if __name__ == "__main__":
    unittest.main()
