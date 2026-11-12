"""Runs started from the app: one at a time, in a background thread, state kept in data/runs/<id>/."""
import json
import re
import threading
from datetime import datetime, timezone

import feedback
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
        paused = _mostly_rejected(latest())  # kill rule against a loop that is making drafts worse
        meta = {"id": run_id, "started_at": _now(), "finished_at": None, "domains": domains,
                "corrections_paused": paused}
        (run_dir / "run.json").write_text(json.dumps(meta, indent=2))

        def work():
            for domain in domains:
                try:
                    pipeline.run_company(domain, run_id, send=False, apply_corrections=not paused)  # sending is the operator's click on Review
                except Exception as e:  # one company failing never stops the run
                    (run_dir / ("%s.json" % domain)).write_text(json.dumps({
                        "domain": domain, "run_id": run_id, "verdict": "flagged", "flags": [],
                        "reason": "Something went wrong researching this company (%s)." % type(e).__name__}))
            meta["finished_at"] = _now()
            (run_dir / "run.json").write_text(json.dumps(meta, indent=2))

        _active["thread"] = threading.Thread(target=work, daemon=True)
        _active["thread"].start()
        return run_id, None


def _ready(r):
    return r.get("verdict") == "qualified" and (r.get("draft") or {}).get("grader_verdict") == "ready"


def _mostly_rejected(run):
    drafts = [r for r in (run or {}).get("records", []) if _ready(r)]
    return bool(drafts) and 2 * sum(1 for r in drafts if (r.get("review") or {}).get("skipped")) > len(drafts)


def loop_summary():
    """Average disagreement over the last 10 drafts the operator acted on (0 = sent untouched, 1 = rejected)."""
    acted = []
    for path in RUNS.glob("*/*.json"):
        if path.name != "run.json":
            review = json.loads(path.read_text()).get("review") or {}
            when = review.get("sent_at") or review.get("skipped_at")
            if when and "disagreement" in review:
                acted.append((when, review["disagreement"]))
    last = [d for _, d in sorted(acted)[-10:]]
    return {"drafts_counted": len(last), "avg_disagreement": round(sum(last) / len(last), 2) if last else None}


def _save_correction(record, review, row):
    row_id, why = feedback.store(row)  # never blocks the send: a failed save is only noted
    review["correction"] = {"saved": row_id is not None, "id": row_id, "note": why}


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


def act(run_id, domain, action, edits=None):
    """send | rewrote | skip on one record. `edits` may carry the operator's subject, body and reason.
    Returns (record, None) or (None, (http code, message))."""
    edits = edits or {}
    if not RUN_ID.match(run_id or "") or action not in ("send", "rewrote", "skip"):
        return None, (400, "Bad request.")
    path = RUNS / run_id / ("%s.json" % domain)
    meta_path = RUNS / run_id / "run.json"
    if not meta_path.exists() or domain not in json.loads(meta_path.read_text())["domains"] or not path.exists():
        return None, (404, "That company is not in this run.")
    with _lock:  # one action at a time, so a double click can never send or store twice
        r = json.loads(path.read_text())
        draft = r.get("draft") or {}
        if not _ready(r):
            return None, (409, "This company has no draft ready to act on.")
        review = r.setdefault("review", {"status": "Qualified"})
        if action == "send" and not review.get("sent_at") and not review.get("skipped"):
            change = None
            if "body" in edits:
                if not edits["body"].strip() or not edits.get("subject", "").strip():
                    return None, (400, "The email needs a subject and a body.")
                change = feedback.compare(draft, edits["subject"], edits["body"])
            if change:
                review["edited"] = {"subject": edits["subject"].strip(), "body": edits["body"].strip() + "\n"}
            subject = review["edited"]["subject"] if change else draft["subject"]
            try:
                send_to_operator("[Draft] %s | %s" % (subject, r.get("name") or domain), pipeline.inbox_email(r))
            except Exception as e:
                review.pop("edited", None)
                review["send_error"] = "Gmail send failed (%s). Try again." % type(e).__name__
                path.write_text(json.dumps(r, indent=2))
                return None, (502, review["send_error"])
            review.update(status="Rewritten" if change or review.get("rewritten") else "Sent to me", sent_at=_now(),
                          disagreement=change["disagreement"] if change else 0.0)
            review.pop("send_error", None)
            if change:  # an untouched draft is no signal and stores nothing
                review.update(rewritten=True, changed_parts=change["changed_parts"])
                _save_correction(r, review, feedback.row_for(r, change, edits.get("reason")))
        elif action == "rewrote":
            review.update(status="Rewritten", rewritten=True)
        elif action == "skip" and not review.get("skipped") and not review.get("sent_at"):
            review.update(skipped=True, skipped_at=_now(), disagreement=1.0)
            _save_correction(r, review, feedback.row_for(r, None, edits.get("reason"), rejected=True))
        path.write_text(json.dumps(r, indent=2))
    r["status"] = status_of(r)
    return r, None
