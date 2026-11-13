"""Weekly kill-criterion check (docs/mesa/brief.md): is the system still worth running?

  python3 metrics.py                         this week's numbers, plus qualified companies to check by hand
  python3 metrics.py --ok dub.co             you checked it: right company, right person
  python3 metrics.py --false-qualify dub.co  it should not have qualified
  python3 metrics.py --wrong-contact dub.co  right company, wrong person
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
MANUAL_MINUTES = 15  # the low end of the 15-20 minutes he spends by hand
SAMPLE = 5
VERDICTS = {"--ok": "ok", "--false-qualify": "false_qualify", "--wrong-contact": "wrong_contact"}


def _when(text):
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def judge(domain, verdict, data=DATA):
    with open(data / "judgements.jsonl", "a") as f:
        f.write(json.dumps({"domain": domain, "verdict": verdict, "at": datetime.now(timezone.utc).isoformat()}) + "\n")


def report(data=DATA, now=None, days=7):
    """The four kill criteria over the last `days`. A rate is None until there is something to measure."""
    since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    companies = acted = rewritten = 0
    seconds = cost = 0.0
    qualified = {}
    for meta_path in sorted((data / "runs").glob("*/run.json")):
        meta = json.loads(meta_path.read_text())
        start, end = _when(meta.get("started_at")), _when(meta.get("finished_at"))
        if not start or start < since:
            continue
        if end and end > start:  # runs with no real duration (rebuilt or interrupted) are left out of the timing
            seconds += (end - start).total_seconds()
            companies += len(meta["domains"])
        for domain in meta["domains"]:
            path = meta_path.parent / ("%s.json" % domain)
            if not path.exists():
                continue
            r = json.loads(path.read_text())
            cost += r.get("claude_cost_usd") or 0
            review = r.get("review") or {}
            if review.get("sent_at") or review.get("skipped"):
                acted += 1
                rewritten += 1 if review.get("rewritten") or review.get("skipped") else 0
            if r.get("verdict") == "qualified":
                qualified[domain] = r
    judged = {}
    path = data / "judgements.jsonl"
    for line in (path.read_text().splitlines() if path.exists() else []):
        j = json.loads(line)
        if (_when(j["at"]) or since) >= since:
            judged[j["domain"]] = j["verdict"]  # the latest judgement on a company wins
    n = len(judged)
    out = {
        "days": days, "drafts_acted_on": acted, "companies_judged": n, "claude_cost_usd": round(cost, 2),
        "rewrite_rate": round(rewritten / acted, 2) if acted else None,
        "false_qualify_rate": round(sum(v == "false_qualify" for v in judged.values()) / n, 2) if n else None,
        "contact_accuracy": round(1 - sum(v == "wrong_contact" for v in judged.values()) / n, 2) if n else None,
        "minutes_per_company": round(seconds / companies / 60, 1) if companies else None,
    }
    out["kill"] = [why for hit, why in (
        (out["rewrite_rate"] is not None and out["rewrite_rate"] > 0.5, "rewrites or skips over 50%"),
        (out["contact_accuracy"] is not None and out["contact_accuracy"] < 0.6, "contact accuracy under 60%"),
        (out["false_qualify_rate"] is not None and out["false_qualify_rate"] > 0.3, "false qualifies over 30%"),
        (out["minutes_per_company"] is not None and out["minutes_per_company"] > MANUAL_MINUTES,
         "slower than doing it by hand"),
    ) if hit]
    out["to_check"] = sorted(set(qualified) - set(judged))
    return out, qualified


def main(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
    import checks
    checks.plain_terminal()
    if args and args[0] in VERDICTS:
        if len(args) != 2:
            sys.exit("%s needs one domain." % args[0])
        judge(args[1], VERDICTS[args[0]])
        print("Recorded: %s is %s." % (args[1], VERDICTS[args[0]].replace("_", " ")))
        return
    if args:
        sys.exit(__doc__)
    out, qualified = report()

    def show(value, as_percent=True):
        return "no data yet" if value is None else ("%d%%" % round(value * 100) if as_percent else str(value))

    print("Last %d days" % out["days"])
    print("  Rewritten or skipped:  %-12s kill above 50%%   (%d drafts acted on)" % (show(out["rewrite_rate"]), out["drafts_acted_on"]))
    print("  Contact accuracy:      %-12s kill below 60%%   (%d companies you checked)" % (show(out["contact_accuracy"]), out["companies_judged"]))
    print("  False qualifies:       %-12s kill above 30%%" % show(out["false_qualify_rate"]))
    print("  Minutes per company:   %-12s kill above %d (by hand)" % (show(out["minutes_per_company"], False), MANUAL_MINUTES))
    print("  Claude cost logged:    $%.2f" % out["claude_cost_usd"])
    print("\nVERDICT: %s" % ("KILL CRITERION HIT: " + "; ".join(out["kill"]) if out["kill"] else "keep running"))
    sample = random.sample(out["to_check"], min(SAMPLE, len(out["to_check"])))
    if sample:
        print("\nCheck these by hand, then record each with --ok, --false-qualify or --wrong-contact:")
        for domain in sample:
            r = qualified[domain]
            who = r.get("contact") or {}
            print("  %-22s %s\n  %-22s contact: %s" % (domain, r.get("qualify_reason") or r.get("reason", ""), "",
                                                    "%s, %s" % (who.get("name"), who.get("position")) if who else "none found"))
    with open(DATA / "kill-log.jsonl", "a") as f:
        f.write(json.dumps(dict(out, at=datetime.now(timezone.utc).isoformat())) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
