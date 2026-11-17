"""Runs started from the app. No background thread: Vercel stops work once a response is sent, so the
Review screen asks for one company at a time (step) until the run is done. State lives in store.STORE."""
import re
import secrets
import threading
from datetime import datetime, timezone

import feedback
import pipeline
import store
from mailer import cc_allowed, send_to_operator

RUN_ID = re.compile(r"^\d{8}-\d{6}(-[0-9a-f]{4})?$")  # the suffix keeps two runs started in the same second apart
STEP_TTL = 330  # seconds: past Vercel's 300 s limit, so a company whose step died can be picked up again
MAX_ATTEMPTS = 2
_lock = threading.Lock()  # local server: one action at a time inside this process; claims cover other processes


def _now():
    return datetime.now(timezone.utc).isoformat()


def new_run_id():
    return "%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), secrets.token_hex(2))


def status_of(r):
    review = r.get("review") or {}
    if review.get("status") in ("Sent to me", "Rewritten"):
        return review["status"]
    return {"qualified": "Qualified", "disqualified": "Disqualified"}.get(r.get("verdict"), "Flagged")


def start(domains, source="pasted", queue=(), target=0):
    """Returns (run_id, None). Research happens in step(). `source`: pasted by the operator, or found by discover.py,
    which also passes spare companies (`queue`) that replace ones ending without a draft until `target` drafts are ready."""
    run_id = new_run_id()
    paused = _mostly_rejected(latest())  # kill rule against a loop that is making drafts worse
    store.STORE.put("run", run_id, {"id": run_id, "started_at": _now(), "finished_at": None, "domains": domains, "source": source, "queue": list(queue), "target": target,
                                    "corrections_paused": paused, "halt": {}, "attempts": {}})
    return run_id, None


def mark_background(run_id):
    """The server is researching this run on its own (discover.kick), so the page can be closed."""
    meta = store.STORE.get("run", run_id)
    if meta and not meta.get("background"):  # once is enough: every later hop would only add another write
        meta["background"] = True
        store.STORE.put("run", run_id, meta)


def step(run_id):
    """Research the next unfinished company in the run, then return the run state. Safe with two tabs open."""
    if not RUN_ID.fullmatch(run_id or ""):
        return None, (400, "Bad request.")
    meta = store.STORE.get("run", run_id)
    if not meta:
        return None, (404, "No such run.")
    for domain in meta["domains"]:
        if store.STORE.get("record", "%s/%s" % (run_id, domain)):
            continue
        if not store.STORE.claim("step:%s:%s" % (run_id, domain), ttl=STEP_TTL):
            continue  # another request is researching it right now
        tries = meta["attempts"].get(domain, 0) + 1
        meta["attempts"][domain] = tries
        store.STORE.put("run", run_id, meta)
        if tries > MAX_ATTEMPTS:  # the step was killed twice (time limit): stop retrying, tell the operator
            _failed(run_id, domain, "Research took too long twice and was stopped.")
        else:
            try:
                pipeline.run_company(domain, run_id, send=False, apply_corrections=not meta["corrections_paused"],
                                     halt=meta["halt"])  # sending is the operator's click on Review
            except Exception as e:  # one company failing never stops the run
                _failed(run_id, domain, "Something went wrong researching this company (%s)." % type(e).__name__)
            fresh = store.STORE.get("run", run_id)  # keep attempts written by other requests, add this halt state
            fresh["halt"] = meta["halt"]
            _top_up(run_id, fresh)
            store.STORE.put("run", run_id, fresh)
        break
    return state(run_id), None


def _top_up(run_id, meta):
    """A found run keeps going until it has its target of drafts: each company that ended without one is replaced by
    the next spare, as long as drafts ready plus companies still open fall short. Hunter's halt stops it too."""
    if not meta.get("queue") or meta.get("halt", {}).get("hunter"):
        return
    recs = [store.STORE.get("record", "%s/%s" % (run_id, d)) for d in meta["domains"]]
    ready, open_ = sum(1 for r in recs if r and _ready(r)), sum(1 for r in recs if not r)
    while meta["queue"] and ready + open_ < meta.get("target", 0):
        meta["domains"].append(meta["queue"].pop(0))
        open_ += 1


def _failed(run_id, domain, reason):
    store.STORE.put("record", "%s/%s" % (run_id, domain),
                    {"domain": domain, "run_id": run_id, "verdict": "flagged", "flags": [], "reason": reason})


def _ready(r):
    return r.get("verdict") == "qualified" and (r.get("draft") or {}).get("grader_verdict") == "ready"


def _mostly_rejected(run):
    drafts = [r for r in (run or {}).get("records", []) if _ready(r)]
    return bool(drafts) and 2 * sum(1 for r in drafts if (r.get("review") or {}).get("skipped")) > len(drafts)


def loop_summary():
    """Average disagreement over the last 10 drafts the operator acted on (0 = sent untouched, 1 = rejected)."""
    acted = []
    for r in store.STORE.records():
        review = r.get("review") or {}
        when = review.get("sent_at") or review.get("skipped_at")
        if when and "disagreement" in review:
            acted.append((when, review["disagreement"]))
    last = [d for _, d in sorted(acted)[-10:]]
    return {"drafts_counted": len(last), "avg_disagreement": round(sum(last) / len(last), 2) if last else None}


def cost_per_company():
    """Measured Claude cost per company, for the estimate on the Run screen."""
    costs = [c for c in (r.get("claude_cost_usd") for r in store.STORE.records()) if c]
    return round(sum(costs) / len(costs), 3) if len(costs) >= 10 else None  # too few to trust: the screen keeps its default


def _save_correction(record, review, row):
    row_id, why = feedback.store(row)  # never blocks the send: a failed save is only noted
    review["correction"] = {"saved": row_id is not None, "id": row_id, "note": why}


def latest():
    ids = [i for i in store.STORE.run_ids() if RUN_ID.fullmatch(i)]
    return state(ids[-1]) if ids else None


def state(run_id):
    meta = store.STORE.get("run", run_id)
    records = []
    for domain in meta["domains"]:
        r = store.STORE.get("record", "%s/%s" % (run_id, domain))
        if r:
            r["status"] = status_of(r)
            records.append(r)
        else:
            records.append({"domain": domain, "status": "Researching", "pending": True})
    if not meta.get("finished_at") and all(not r.get("pending") for r in records):
        meta["finished_at"] = _now()  # the step that finishes the last company calls state() right away
        meta.pop("records", None)
        store.STORE.put("run", run_id, meta)
    meta["records"] = records
    meta["hunter_searches_used"] = sum(1 for r in records if r.get("hunter_search_spent"))
    return meta


def act(run_id, domain, action, edits=None):
    """send | rewrote | skip | note on one record. `edits` may carry the operator's subject, body, reason, the people
    he marked as CC, or a note about one person. Returns (record, None) or (None, (http code, message))."""
    edits = edits or {}
    if not RUN_ID.fullmatch(run_id or "") or action not in ("send", "rewrote", "skip", "note", "people"):
        return None, (400, "Bad request.")
    meta = store.STORE.get("run", run_id)
    key = "%s/%s" % (run_id, domain)
    if not meta or domain not in meta["domains"] or not store.STORE.get("record", key):
        return None, (404, "That company is not in this run.")
    for k in ("subject", "body", "reason", "note", "person"):  # checked here too, before any email goes out
        if k in edits and not isinstance(edits[k], str):
            return None, (400, "Bad request.")
    with _lock:
        r = store.STORE.get("record", key)
        draft = r.get("draft") or {}
        known = {o["email"] for o in r.get("others") or []}  # a CC or a note can only name someone Hunter found here
        if action == "people":  # the operator's click: one more Hunter search, for everyone at this company
            if not r.get("contact"):
                return None, (409, "This company has no contact to build a map around.")
            try:
                first = (store.STORE.get("cache", domain + "/hunter") or {}).get("people") or []
                wide, _ = pipeline.hunter_people(domain, wide=True)
            except RuntimeError as e:  # HunterStop included: no key, no searches left, or no answer
                return None, (502, str(e))
            r["others"], r["others_searched"] = pipeline.others_found(first + wide, r["contact"]), True
            store.STORE.put("record", key, r)
            r["status"] = status_of(r)
            return r, None
        if action == "note":
            person = edits.get("person")
            if not r.get("contact") or person not in known | {r["contact"]["email"]}:
                return None, (400, "That person is not on this company's map.")
            notes = r.setdefault("notes", {})
            notes[person] = (edits.get("note") or "").strip()[:feedback.MAX_REASON]
            if not notes[person]:
                del notes[person]
            store.STORE.put("record", key, r)
            r["status"] = status_of(r)
            return r, None
        cc = edits.get("cc") or []
        if not isinstance(cc, list) or len(cc) > pipeline.MAX_OTHERS or any(e not in known for e in cc):
            return None, (400, "A CC must be someone on this company's map.")
        if not _ready(r):
            return None, (409, "This company has no draft ready to act on.")
        review = r.setdefault("review", {"status": "Qualified"})
        again = bool(review.get("sent_at"))  # a sent draft the operator edited and sends again: a new version, never a repeat
        if action == "send" and not review.get("skipped") and (not again or "body" in edits):
            change = None
            if "body" in edits:
                if not edits["body"].strip() or not edits.get("subject", "").strip():
                    return None, (400, "The email needs a subject and a body.")
                change = feedback.compare(draft, edits["subject"], edits["body"])
            last = review.get("edited") or {}
            if again and (not change or (last.get("subject"), last.get("body")) == (edits["subject"].strip(), edits["body"].strip() + "\n")):
                return None, (409, "Nothing changed since the last send. Edit the email first.")
            version = review.get("versions_sent", 1) + 1 if again else 1
            claim = "send:" + key + ("" if version == 1 else ":%d" % version)
            if not store.STORE.claim(claim):  # across serverless instances: one email per version
                return None, (409, "This draft is already being sent.")
            previous = {k: review.get(k) for k in ("edited", "cc", "cc_delivered")}
            if change:
                review["edited"] = {"subject": edits["subject"].strip(), "body": edits["body"].strip() + "\n"}
            subject = review["edited"]["subject"] if change else draft["subject"]
            deliver = [e for e in cc if cc_allowed(e)]
            review.update(cc=cc, cc_delivered=deliver)
            try:
                args = (pipeline.subject_line(subject, r.get("name") or domain), pipeline.inbox_email(r))
                send_to_operator(*args, cc=deliver) if deliver else send_to_operator(*args)
            except Exception as e:
                store.STORE.release(claim)  # nothing went out: allow a retry
                for k, v in previous.items():  # back to what was last sent
                    review.pop(k, None) if v is None else review.update({k: v})
                review["send_error"] = "Gmail send failed (%s). Try again." % type(e).__name__
                store.STORE.put("record", key, r)
                return None, (502, review["send_error"])
            review.update(status="Rewritten" if change or review.get("rewritten") else "Sent to me", sent_at=_now(),
                          disagreement=change["disagreement"] if change else 0.0, versions_sent=version)
            review.pop("send_error", None)
            if change:  # an untouched draft is no signal and stores nothing
                review.update(rewritten=True, changed_parts=change["changed_parts"])
                _save_correction(r, review, feedback.row_for(r, change, edits.get("reason")))
        elif action == "rewrote":
            review.update(status="Rewritten", rewritten=True)
        elif action == "skip" and not review.get("skipped") and not review.get("sent_at"):
            review.update(skipped=True, skipped_at=_now(), disagreement=1.0)
            _save_correction(r, review, feedback.row_for(r, None, edits.get("reason"), rejected=True))
        store.STORE.put("record", key, r)
    r["status"] = status_of(r)
    return r, None
