import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from pipeline import email_body, pick_contact, qualify, role_tier  # noqa: E402

BASE = {"certified": "unknown", "certified_quote": "", "certified_in_progress": False,
        "b2b_saas": "yes", "b2b_saas_quote": "Workflow software for finance teams",
        "stage": "Series A", "stage_quote": "backed by our $18M Series A", "trigger": "unknown", "trigger_quote": "",
        "funding_round": "series-a", "funding_round_quote": "backed by our $18M Series A",
        "team_size": 0, "team_size_quote": "", "enterprise_signal": False, "enterprise_signal_quote": ""}


def person(position, confidence=90, status="valid", first="Asha"):
    return {"first_name": first, "last_name": "Rao", "value": "a@x.io", "position": position,
            "confidence": confidence, "verification": {"status": status}}


class Qualify(unittest.TestCase):
    def test_certified_disqualifies_first(self):
        f = dict(BASE, certified="yes", certified_quote="SOC 2 Type II certified", b2b_saas="no")
        self.assertEqual(qualify(f)[:2], ("disqualified", "already certified"))

    def test_not_b2b_saas_disqualifies(self):
        self.assertEqual(qualify(dict(BASE, b2b_saas="no"))[:2], ("disqualified", "not B2B SaaS"))

    def test_unclear_b2b_is_flagged(self):
        self.assertEqual(qualify(dict(BASE, b2b_saas="unknown"))[0], "flagged")

    def test_qualifies_with_flags_for_unknowns(self):
        verdict, _, _, flags = qualify(dict(BASE, stage="unknown"))
        self.assertEqual(verdict, "qualified")
        self.assertEqual(len(flags), 2)  # certification not stated, no growth signal

    def test_in_progress_qualifies_with_flag(self):
        verdict, _, _, flags = qualify(dict(BASE, certified="no", certified_in_progress=True))
        self.assertEqual(verdict, "qualified")
        self.assertIn("competing tool", flags[0])


class Contact(unittest.TestCase):
    def test_role_words_match_whole_words_only(self):
        self.assertEqual(role_tier("Director of Sales")[0], None)  # "direCTOr" is not CTO
        self.assertEqual(role_tier("CTO & Co-founder")[0], 2)
        self.assertEqual(role_tier("Head of Security")[0], 1)
        self.assertEqual(role_tier("Co-CEO")[0], 4)

    def test_role_beats_seniority_and_filters_apply(self):
        people = [person("CEO", 99), person("VP Engineering", 80, first="Ben"),
                  person("Head of Compliance", 60, first="Low"), person("CISO", 95, "invalid", first="Bad"),
                  person(None, 99, first="Untitled")]
        contact, considered = pick_contact(people)
        self.assertEqual(contact["first_name"], "Ben")
        self.assertEqual(considered, 5)

    def test_no_usable_contact(self):
        self.assertIsNone(pick_contact([person(None), person("Designer")])[0])

    def test_ties_go_to_higher_confidence(self):
        contact, _ = pick_contact([person("CTO", 75, first="A"), person("VP of Engineering", 88, first="B")])
        self.assertEqual(contact["first_name"], "B")


class Body(unittest.TestCase):
    def test_body_has_greeting_and_four_parts(self):
        body = email_body("Asha", {"hook": "H.", "pain": "P.", "value": "V.", "ask": "A?"})
        self.assertEqual(body, "Hi Asha,\n\nH. P.\n\nV.\n\nA?\n")


if __name__ == "__main__":
    unittest.main()
