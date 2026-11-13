"""Run the pipeline from the terminal (the app's Run and Review screens do the same with a click).

  python3 run.py acme.com other.io               run, send drafts to your own inbox
  python3 run.py --writer haiku --no-send acme.com   cheaper writer, keep drafts local
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
import checks  # noqa: E402
from claude import HAIKU, SONNET  # noqa: E402
from domains import parse_domains  # noqa: E402
from pipeline import run_company  # noqa: E402
import runs  # noqa: E402
import store  # noqa: E402


def main(args):
    checks.plain_terminal()
    writer = SONNET
    if "--writer" in args:
        i = args.index("--writer")
        writer = {"haiku": HAIKU, "sonnet": SONNET}.get(args[i + 1] if i + 1 < len(args) else "")
        if not writer:
            sys.exit("--writer takes haiku or sonnet.")
        args = args[:i] + args[i + 2:]
    send = "--no-send" not in args
    args = [a for a in args if a != "--no-send"]
    parsed = parse_domains(" ".join(args))
    for bad in parsed["rejected"]:
        print("SKIPPED %s: %s" % (bad["input"], bad["reason"]))
    checks.load_env()
    run_id = runs.new_run_id()  # the random suffix keeps it apart from a run the app starts in the same second
    meta = {"id": run_id, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
            "domains": parsed["valid"], "corrections_paused": False, "halt": {}, "attempts": {}}
    store.STORE.put("run", run_id, meta)  # so the Review screen can show terminal runs too
    halt = meta["halt"]
    for domain in parsed["valid"]:
        r = run_company(domain, run_id, writer=writer, send=send, halt=halt)
        status = (r.get("review") or {}).get("status") or r["verdict"]
        print("%-12s %-24s %s" % (status.upper(), domain, r["reason"]))
        if r.get("draft", {}).get("body"):
            print("  to %s (%s)\n  subject: %s\n%s" % (r["contact"]["name"], r["contact"]["position"],
                                                      r["draft"]["subject"], r["draft"]["body"]))
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    store.STORE.put("run", run_id, meta)
    print("Records: data/runs/%s/" % run_id)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
