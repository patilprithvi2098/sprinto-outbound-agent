"""Phase 0 feasibility test (answers Nine Checks #03: is the input available?).

  python3 feasibility.py acme.com other.io          fetch each homepage, report whether it is readable
  python3 feasibility.py --hunter acme.com          ALSO spend ONE Hunter search on acme.com
"""
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
import checks  # noqa: E402
from domains import parse_domains  # noqa: E402
from scrape import fetch  # noqa: E402


def main(args):
    hunter_domain = None
    if "--hunter" in args:
        i = args.index("--hunter")
        hunter_domain = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
        if not hunter_domain:
            sys.exit("--hunter needs a domain.")
    parsed = parse_domains(" ".join(args + ([hunter_domain] if hunter_domain else [])))
    for bad in parsed["rejected"]:
        print("SKIPPED  %-30s %s" % (bad["input"], bad["reason"]))

    for domain in parsed["valid"]:
        page = fetch("https://%s/" % domain)
        if page["ok"]:
            print("READABLE %-30s %d words of clean text" % (domain, page["words"]))
        else:
            print("FAILED   %-30s %s" % (domain, page["reason"]))

    if hunter_domain and hunter_domain in parsed["valid"]:
        checks.load_env()
        key = os.environ.get("HUNTER_API_KEY")
        if not key:
            sys.exit("HUNTER_API_KEY is not set in .env.")
        query = urllib.parse.urlencode({"domain": hunter_domain, "limit": 10, "api_key": key})
        try:
            data = checks.get_json("https://api.hunter.io/v2/domain-search?" + query)["data"]
        except Exception as e:
            sys.exit("Hunter search failed (%s)." % type(e).__name__)  # no URL in the message: it holds the key
        people = data.get("emails", [])
        print("\nHunter returned %d people for %s (1 search spent):" % (len(people), hunter_domain))
        for p in people:
            print("  %-28s confidence %-3s %s" % (
                p.get("position") or "(no title)", p.get("confidence"),
                (p.get("verification") or {}).get("status") or "unverified"))
        titled = sum(1 for p in people if p.get("position"))
        print("%d of %d have a job title, which the role-priority rule needs." % (titled, len(people)))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
