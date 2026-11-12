"""Phase 1 pipeline, homepage only: extract -> qualify -> Hunter -> pick person -> pains and draft -> own inbox -> record."""
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import checks
from claude import HAIKU, SONNET, ClaudeError, ask_json
from mailer import send_to_operator
from scrape import fetch

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = json.loads((ROOT / "config" / "icp.json").read_text())
PAGE_CHARS = 8000  # about 2,000 tokens of cleaned text per page
HUNTER_CACHE_DAYS = 7
_YNU = {"type": "string", "enum": ["yes", "no", "unknown"]}


def _prompt(name):
    return (ROOT / "prompts" / ("%s.md" % name)).read_text()


def _strict(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


EXTRACT_SCHEMA = _strict({
    "company_name": {"type": "string"}, "what_it_does": {"type": "string"},
    "certified": _YNU, "certified_quote": {"type": "string"}, "certified_in_progress": {"type": "boolean"},
    "b2b_saas": _YNU, "b2b_saas_quote": {"type": "string"},
    "stage": {"type": "string"}, "stage_quote": {"type": "string"},
    "trigger": {"type": "string"}, "trigger_quote": {"type": "string"},
})
WRITE_SCHEMA = _strict({
    "can_write": {"type": "boolean"}, "missing_field": {"type": "string"},
    "pains": {"type": "array", "items": _strict({"pain": {"type": "string"}, "evidence_field": {"type": "string"}})},
    "role_measured_on": {"type": "string"},
    "subject": {"type": "string"}, "hook": {"type": "string"}, "pain": {"type": "string"},
    "value": {"type": "string"}, "ask": {"type": "string"},
})


def _known(value):
    return bool(value) and value.strip().lower() != "unknown"


def extract(page_text, url):
    fields = ask_json(HAIKU, _prompt("extract"), "URL: %s\n<page>\n%s\n</page>" % (url, page_text[:PAGE_CHARS]),
                      EXTRACT_SCHEMA, effort="low")
    for name in ("certified", "b2b_saas", "stage", "trigger"):  # a fact without its quote does not count
        if _known(fields[name]) and not fields[name + "_quote"].strip():
            fields[name] = "unknown"
    return fields


def qualify(f):
    """Code decides, first match wins. Returns (verdict, rule, reason, flags)."""
    if f["certified"] == "yes":
        return "disqualified", "already certified", 'Homepage says: "%s"' % f["certified_quote"], []
    if f["b2b_saas"] == "no":
        return "disqualified", "not B2B SaaS", 'Homepage says: "%s"' % f["b2b_saas_quote"], []
    if f["b2b_saas"] != "yes":
        return "flagged", "unclear if B2B SaaS", "The homepage does not show who it sells to.", []
    flags = []
    if f["certified_in_progress"]:
        flags.append("certification in progress: may already use a competing tool")
    elif f["certified"] == "unknown":
        flags.append("no certification stated on the homepage (treated as not certified)")
    if not _known(f["stage"]):
        flags.append("no growth or enterprise signal found: lower rank")
    reason = 'B2B SaaS ("%s") with no certification shown' % f["b2b_saas_quote"]
    if _known(f["stage"]):
        reason += '; growth signal: "%s"' % f["stage_quote"]
    return "qualified", "B2B SaaS, not certified", reason, flags


def role_tier(position):
    text = (position or "").lower()
    for role in CONFIG["role_priority"]:
        if any(re.search(r"\b%s\b" % re.escape(k), text) for k in role["keywords"]):
            return role["tier"], role["label"]
    return None, None


def pick_contact(people):
    """Rank Hunter people by role priority, not seniority; ties go to higher confidence."""
    candidates = []
    for p in people:
        status = (p.get("verification") or {}).get("status")
        tier, label = role_tier(p.get("position"))
        if status == "invalid" or (p.get("confidence") or 0) < CONFIG["min_confidence"] or tier is None:
            continue  # untitled people cannot be ranked by role, so they are skipped
        candidates.append((tier, -(p.get("confidence") or 0), label, p))
    if not candidates:
        return None, len(people)
    tier, _, label, p = min(candidates, key=lambda c: c[:2])
    return {
        "name": " ".join(filter(None, [p.get("first_name"), p.get("last_name")])),
        "first_name": p.get("first_name") or "", "position": p.get("position"), "email": p.get("value"),
        "confidence": p.get("confidence"), "verification_status": (p.get("verification") or {}).get("status"),
        "role_tier": tier,
        "why_this_person": "Highest on the role priority list (tier %d, %s) among %d usable of %d people Hunter found."
                           % (tier, label, len(candidates), len(people)),
    }, len(people)


def hunter_people(domain):
    """One Hunter search per domain, reused for 7 days so a re-run never spends twice."""
    cache = DATA / "cache" / domain / "hunter.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < HUNTER_CACHE_DAYS * 86400:
        return json.loads(cache.read_text()), False
    quota = checks.check_hunter()
    if not quota["ok"]:
        raise RuntimeError(quota["detail"])
    if quota["searches_left"] <= 0:
        raise RuntimeError("Hunter has no searches left this month.")
    query = urllib.parse.urlencode({"domain": domain, "limit": 10, "api_key": os.environ["HUNTER_API_KEY"]})
    try:
        people = checks.get_json("https://api.hunter.io/v2/domain-search?" + query)["data"].get("emails", [])
    except Exception as e:
        raise RuntimeError("Hunter search failed (%s)." % type(e).__name__)  # no URL: it holds the key
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(people))
    return people, True


def write_draft(pack, model):
    system = _prompt("write").replace("{banned}", "; ".join(CONFIG["banned_phrases"]))
    return ask_json(model, system, "<pack>\n%s\n</pack>" % json.dumps(pack, indent=1), WRITE_SCHEMA, effort="high")


def email_body(first_name, d):
    return "Hi %s,\n\n%s %s\n\n%s\n\n%s\n" % (first_name, d["hook"], d["pain"], d["value"], d["ask"])


def inbox_email(record):
    """The draft first, the reasoning directly under it."""
    r, c, d = record, record["contact"], record["draft"]
    lines = [email_body(c["first_name"], d), "-" * 40, "DRAFT ONLY. Nothing was sent to this person.",
             "Would go to: %s, %s <%s> (Hunter confidence %s, %s)" % (c["name"], c["position"], c["email"],
                                                                     c["confidence"], c["verification_status"]),
             "", "Why this company: %s (%s)" % (r["reason"], r["pages_fetched"][0]),
             "Why this person: %s" % c["why_this_person"],
             "Pain 1: %s [from %s]" % (d["pains"][0]["pain"], d["pains"][0]["evidence_field"]),
             "Pain 2: %s [from %s]" % (d["pains"][1]["pain"], d["pains"][1]["evidence_field"]),
             "This role is measured on: %s" % d["role_measured_on"],
             'Hook built from: "%s"' % r["fields"]["trigger_quote"]]
    if r["flags"]:
        lines.append("Flags: " + "; ".join(r["flags"]))
    lines += ["Writer model: %s" % d["model"], "Decision record: %s" % r["record_path"]]
    return "\n".join(lines)


def run_company(domain, run_id, writer=SONNET, send=True):
    run_dir = DATA / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / ("%s.json" % domain)
    url = "https://%s/" % domain
    record = {"domain": domain, "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
              "pages_fetched": [url], "extra_fetches_used": 0, "flags": [],
              "record_path": str(path.relative_to(ROOT))}

    def done(verdict, reason, **extra):
        record.update(verdict=verdict, reason=reason, **extra)
        path.write_text(json.dumps(record, indent=2))
        return record

    page = fetch(url)
    if not page["ok"]:
        return done("flagged", page["reason"], rule_applied="scrape failed", failure_reason=page["reason"])
    try:
        fields = extract(page["text"], url)
    except ClaudeError as e:
        return done("flagged", str(e), rule_applied="extraction failed")
    record["name"], record["fields"] = fields["company_name"], fields
    verdict, rule, reason, flags = qualify(fields)
    record["flags"] = flags
    if verdict != "qualified":
        return done(verdict, reason, rule_applied=rule)  # disqualified or unclear: no Hunter, no email
    if not _known(fields["trigger"]):  # checked before Hunter so no search is spent on an email we cannot write
        return done("flagged", "CANNOT WRITE THIS EMAIL: no trigger found on the homepage.", rule_applied=rule,
                    draft={"refusal": "missing field: trigger"})

    try:
        people, spent = hunter_people(domain)
    except RuntimeError as e:
        return done("flagged", str(e), rule_applied=rule)
    record["hunter_search_spent"] = spent
    contact, considered = pick_contact(people)
    record["candidates_considered"] = considered
    if not contact:
        return done("flagged", "No suitable contact: nobody with a ranked role, confidence %d+ and a valid email."
                    % CONFIG["min_confidence"], rule_applied=rule)
    record["contact"] = contact
    pack ={"company": fields["company_name"], "what_it_does": fields["what_it_does"], "source_page": url,
            "facts": {k: {"value": fields[k], "quote": fields[k + "_quote"]}
                      for k in ("b2b_saas", "stage", "trigger") if _known(fields[k])},
            "contact": {"first_name": contact["first_name"], "position": contact["position"],
                        "why_this_person": contact["why_this_person"]}}
    try:
        draft = write_draft(pack, writer)
    except ClaudeError as e:
        return done("flagged", str(e), rule_applied=rule)
    draft["model"] = writer
    if not draft["can_write"] or len(draft["pains"]) < 2:
        return done("flagged", "CANNOT WRITE THIS EMAIL: missing %s." % (draft["missing_field"] or "a usable fact"),
                    rule_applied=rule, draft=dict(draft, refusal=draft["missing_field"]))
    draft["body"] = email_body(contact["first_name"], draft)
    record.update(verdict="qualified", reason=reason, rule_applied=rule, draft=draft, pack=pack)
    if send:
        try:
            send_to_operator("[Draft] %s | %s" % (draft["subject"], fields["company_name"]), inbox_email(record))
            record["review"] = {"status": "Sent to me", "sent_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            record["review"] = {"status": "Qualified", "send_error": "Gmail send failed (%s)." % type(e).__name__}
    return done("qualified", reason)
