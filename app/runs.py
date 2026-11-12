"""Runs started from the app: one at a time, in a background thread, state kept in data/runs/<id>/."""
import json
import re
import threading
from datetime import datetime, timezone

import pipeline
from mailer import send_to_operator

RUNS = pipeline.DATA / "runs"
RUN_ID = re.compile(r"^\d{8}-\d{6}$")
_lock = threading.Lock()
_active = {"thread": None}


def _now():
    return datetime.now(timezone.utc).isoformat()


def status_of(r):
    review = r.get("review") or {}
    if review.get("status") in ("Sent to me", "Rewritten"):
        return review["status"]
    return {"qualified": "Qualified", "disqualified": "Disqualified"}.get(r.get("verdict"), "Flagged")


def start(domains):
    """Returns (run_id, None) or (None, error message)."""
    with _lock:
        if _active["thread"] and _active["thread"].is_alive():
            return None, "A run is already going. Wait for it to finish."
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        meta = {"id": run_id, "started_at": _now(), "finished_at": None, "domains": domains}
        (run_dir / "run.json").write_text(json.dumps(meta, indent=2))

        def work():
            for domain in domains:
                try:
                    pipeline.run_company(domain, run_id, send=False)  # sending is the operator's click on Review
                except Exception as e:  # one company failing never stops the run
                    (run_dir / ("%s.json" % domain)).write_text(json.dumps({
                        "domain": domain, "run_id": run_id, "verdict": "flagged", "flags": [],
                        "reason": "Something went wrong researching this company (%s)." % type(e).__name__}))
            meta["finished_at"] = _now()
            (run_dir / "run.json").write_text(json.dumps(meta, indent=2))

        _active["thread"] = threading.Thread(target=work, daemon=True)
        _active["thread"].start()
        return run_id, None


def latest():
    ids = sorted(p.name for p in RUNS.glob("*") if RUN_ID.match(p.name) and (p / "run.json").exists())
    return state(ids[-1]) if ids else None


def state(run_id):
    run_dir = RUNS / run_id
    meta = json.loads((run_dir / "run.json").read_text())
    records = []
    for domain in meta["domains"]:
        path = run_dir / ("%s.json" % domain)
        if path.exists():
            r = json.loads(path.read_text())
            r["status"] = status_of(r)
            records.append(r)
        else:
            records.append({"domain": domain, "status": "Researching", "pending": True})
    if not meta["finished_at"] and not (_active["thread"] and _active["thread"].is_alive()):
        meta["interrupted"] = True  # the server stopped mid-run
    meta["records"] = records
    meta["hunter_searches_used"] = sum(1 for r in records if r.get("hunter_search_spent"))
    return meta


def act(run_id, domain, action):
    """send | rewrote | skip on one record. Returns (record, None) or (None, (http code, message))."""
    if not RUN_ID.match(run_id or "") or action not in ("send", "rewrote", "skip"):
        return None, (400, "Bad request.")
    path = RUNS / run_id / ("%s.json" % domain)
    meta_path = RUNS / run_id / "run.json"
    if not meta_path.exists() or domain not in json.loads(meta_path.read_text())["domains"] or not path.exists():
        return None, (404, "That company is not in this run.")
    with _lock:  # one action at a time, so a double click can never send twice
        r = json.loads(path.read_text())
        draft = r.get("draft") or {}
        if r.get("verdict") != "qualified" or draft.get("grader_verdict") != "ready":
            return None, (409, "This company has no draft ready to act on.")
        review = r.setdefault("review", {"status": "Qualified"})
        if action == "send" and review.get("status") not in ("Sent to me",) and not review.get("sent_at"):
            try:
                send_to_operator("[Draft] %s | %s" % (draft["subject"], r.get("name") or domain),
                                 pipeline.inbox_email(r))
            except Exception as e:
                review["send_error"] = "Gmail send failed (%s). Try again." % type(e).__name__
                path.write_text(json.dumps(r, indent=2))
                return None, (502, review["send_error"])
            review.update(status="Rewritten" if review.get("rewritten") else "Sent to me", sent_at=_now())
            review.pop("send_error", None)
        elif action == "rewrote":
            review.update(status="Rewritten", rewritten=True)
        elif action == "skip":
            review["skipped"] = True
        path.write_text(json.dumps(r, indent=2))
    r["status"] = status_of(r)
    return r, None
