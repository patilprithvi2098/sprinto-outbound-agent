"""Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from domains import MAX_DOMAINS, parse_domains  # noqa: E402
from scrape import Blocked, assert_public, clean  # noqa: E402


class Domains(unittest.TestCase):
    def test_cleans_and_dedupes(self):
        out = parse_domains("https://www.Kestrelmetrics.io/pricing?x=1, tallybook.co\nkestrelmetrics.io")
        self.assertEqual(out["valid"], ["kestrelmetrics.io", "tallybook.co"])
        self.assertEqual(out["rejected"][0]["reason"], "Duplicate of a domain already in the list.")

    def test_rejects_non_domains_and_private_hosts(self):
        out = parse_domains("meera@orbitly.app localhost 127.0.0.1 nas.local not_a_domain http://10.0.0.5:8080/admin")
        self.assertEqual(out["valid"], [])
        self.assertEqual(len(out["rejected"]), 6)

    def test_caps_the_run(self):
        out = parse_domains("\n".join("company%d.com" % i for i in range(MAX_DOMAINS + 3)))
        self.assertEqual(len(out["valid"]), MAX_DOMAINS)
        self.assertEqual(len(out["rejected"]), 3)

    def test_empty_and_long_input(self):
        self.assertEqual(parse_domains("   ")["valid"], [])
        self.assertEqual(len(parse_domains("a" * 5000)["rejected"][0]["input"]), 80)


class Scrape(unittest.TestCase):
    def test_clean_keeps_footer_badge_and_drops_noise(self):
        html = ("<nav>Home Pricing Login</nav><script>track()</script><h1>Payroll for clinics</h1>"
                "<p>Payroll for clinics</p><footer>SOC 2 Type II certified</footer>")
        self.assertEqual(clean(html), "Payroll for clinics\nSOC 2 Type II certified")

    def test_private_addresses_are_refused(self):
        for host in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"):
            with self.assertRaises(Blocked):
                assert_public(host)


if __name__ == "__main__":
    unittest.main()
