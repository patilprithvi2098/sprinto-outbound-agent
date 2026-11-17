"""Pipeline: research loop -> qualify -> Hunter -> pick person -> pains and draft -> grade -> own inbox -> record."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import checks
import claude
import feedback
import store
from claude import HAIKU, SONNET, ClaudeError, ask_json
from mailer import send_to_operator
from scrape import fetch

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = json.loads((ROOT / "config" / "icp.json").read_text())
PAGE_CHARS = 8000  # about 2,000 tokens of cleaned text per page
CACHE_DAYS = 7
FETCH_DELAY = 1.5  # seconds between live requests to the same site
MIN_QUOTE = 10  # characters after normalising: "soc 2" alone would match almost any security page
FIELDS = ("certified", "b2b_saas", "stage", "trigger")
LABELS = ["FROM PACK", "GENERIC", "MADE UP", "BANNED"]
_YNU = {"type": "string", "enum": ["yes", "no", "unknown"]}
CERT_HELD = re.compile(r"(soc ?2|iso(/iec)? ?27001).*\b(certified|compliant|type (2|ii)|attest\w*|audited|achieved)\b"
                       r"|\b(certified|compliant|achieved)\b.*(soc ?2|iso(/iec)? ?27001)", re.I)
CERT_PENDING = re.compile(r"\b(progress|working towards?|pursuing|planned|plan to|upcoming|soon|not yet|not currently"
                          r"|don't|do not|aren't|isn't|no)\b", re.I)
_ROUNDS = ["pre-seed", "seed", "series-a", "series-b", "series-c-or-later", "public", "unknown"]


def _prompt(name):
    return (ROOT / "prompts" / ("%s.md" % name)).read_text().replace("{banned}", "; ".join(CONFIG["banned_phrases"]))


def _strict(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


_S = {"type": "string"}
EXTRACT_SCHEMA = _strict({
    "company_name": _S, "what_it_does": _S,
    "certified": _YNU, "certified_quote": _S, "certified_in_progress": {"type": "boolean"},
    "b2b_saas": _YNU, "b2b_saas_quote": _S, "stage": _S, "stage_quote": _S,
    "funding_round": {"type": "string", "enum": _ROUNDS}, "funding_round_quote": _S,
    "team_size": {"type": "integer"}, "team_size_quote": _S,
    "enterprise_signal": {"type": "boolean"}, "enterprise_signal_quote": _S,
    "trigger": _S, "trigger_quote": _S,
})
WRITE_SCHEMA = _strict({
    "can_write": {"type": "boolean"}, "missing_field": _S,
    "pains": {"type": "array", "items": _strict({"pain": _S, "evidence_field": _S})},
    "role_measured_on": _S, "subject": _S, "hook": _S, "pain": _S, "value": _S, "ask": _S,
})
GRADE_SCHEMA = _strict({"labels": {"type": "array", "items": _strict({
    "n": {"type": "integer"}, "label": {"type": "string", "enum": LABELS}, "pack_field": _S, "note": _S})}})


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def data(text):
    """Untrusted text placed inside our <tags>: it cannot close a tag and pose as another block."""
    return text.replace("<", "\u2039").replace(">", "\u203a")


def _known(value):
    return bool(value) and value.strip().lower() != "unknown"


def _filled(fields, name):
    return fields[name] in ("yes", "no") if name in ("certified", "b2b_saas") else _known(fields[name])


# ---------- research loop ----------

def get_page(domain, path):
    """One page, cleaned, reused for 7 days. Never raises."""
    key = "%s/%s" % (domain, path.strip("/").replace("/", "_") or "home")
    cached = store.STORE.get("cache", key)
    if cached and time.time() - cached["saved"] < CACHE_DAYS * 86400:
        return {"ok": True, "reason": "", "text": cached["text"], "cached": True}
    if path != "/":
        time.sleep(FETCH_DELAY)
    page = fetch("https://%s%s" % (domain, path))
    if page["ok"]:
        store.STORE.put("cache", key, {"saved": time.time(), "text": page["text"]})
    return dict(page, cached=False)


def extract(page_text, url):
    fields = ask_json(HAIKU, _prompt("extract"), "URL: %s\n<page>\n%s\n</page>" % (url, data(page_text[:PAGE_CHARS])),
                      EXTRACT_SCHEMA, effort="medium")  # low effort missed audit wording (retool.com, Phase 6)
    page = _norm(page_text)
    for name in FIELDS + ("funding_round", "team_size", "enterprise_signal"):
        quote = _norm(fields[name + "_quote"])
        if quote not in page or len(quote) < MIN_QUOTE:  # a paraphrase, or two common words, is not evidence
            fields[name + "_quote"] = ""
    for name in FIELDS:  # a fact without its quote does not count
        if _filled(fields, name) and not fields[name + "_quote"].strip():
            fields[name] = "unknown"
    if fields["certified"] != "yes" and not fields["certified_in_progress"] and CERT_HELD.search(fields["certified_quote"]) \
            and not CERT_PENDING.search(fields["certified_quote"]):
        fields["certified"] = "yes"  # backstop: the quote itself names a held certification
    if not fields["funding_round_quote"].strip():
        fields["funding_round"] = "unknown"
    if not fields["team_size_quote"].strip():
        fields["team_size"] = 0
    if not fields["enterprise_signal_quote"].strip():
        fields["enterprise_signal"] = False
    return fields


def merge(fields, new, url, evidence):
    """Fill gaps from a new page; a certification found anywhere wins. Returns the merged fields."""
    if fields is None:
        fields = dict(new)
        for name in FIELDS + ("funding_round", "enterprise_signal"):
            if (_filled(new, name) if name in FIELDS else new[name] not in ("unknown", False)):
                evidence.append({"field": name, "quote": new[name + "_quote"], "page_url": url})
        if new["team_size"]:
            evidence.append({"field": "team_size", "quote": new["team_size_quote"], "page_url": url})
        return fields
    for name in FIELDS:
        if _filled(new, name) and (not _filled(fields, name) or (name == "certified" and new[name] == "yes")):
            fields[name], fields[name + "_quote"] = new[name], new[name + "_quote"]
            evidence.append({"field": name, "quote": new[name + "_quote"], "page_url": url})
    fields["certified_in_progress"] = fields["certified_in_progress"] or new["certified_in_progress"]
    for name, empty in (("funding_round", "unknown"), ("team_size", 0), ("enterprise_signal", False)):
        if fields[name] == empty and new[name] != empty:
            fields[name], fields[name + "_quote"] = new[name], new[name + "_quote"]
            evidence.append({"field": name, "quote": new[name + "_quote"], "page_url": url})
    return fields


def research(domain, get=get_page, read=extract):
    """Homepage first, then code picks the page where each missing fact lives, up to the fetch cap.
    The model only reads pages; it never decides whether there is enough."""
    pages, evidence = [], []
    home = get(domain, "/")
    pages.append({"url": "https://%s/" % domain, "ok": home["ok"], "reason": home["reason"]})
    if not home["ok"]:
        return {"ok": False, "reason": home["reason"], "pages": pages}
    fields = merge(None, read(home["text"], pages[0]["url"]), pages[0]["url"], evidence)
    used, tried, extra = {}, {"/"}, 0
    while True:
        if fields["certified"] == "yes" or fields["b2b_saas"] == "no":
            stop = "stopped early: a disqualifying fact was found"
            break
        missing = [e for e in CONFIG["evidence_map"] if not _filled(fields, e["field"])]
        if not missing:
            stop = "all fields filled"
            break
        if extra >= CONFIG["max_extra_fetches"]:
            stop = "cap reached (%d extra pages) with %s still unknown" % (extra, ", ".join(e["field"] for e in missing))
            break
        choice = next(((e, p) for e in missing if used.get(e["field"], 0) < e["max_fetches"]
                       for p in e["pages"] if p not in tried), None)
        if not choice:
            stop = "no more pages to try for %s" % ", ".join(e["field"] for e in missing)
            break
        entry, path = choice
        tried.add(path)
        extra += 1  # every attempt, 404s included, counts toward the total cap
        page = get(domain, path)
        url = "https://%s%s" % (domain, path)
        pages.append({"url": url, "ok": page["ok"], "reason": page["reason"], "looking_for": entry["field"]})
        if page["ok"]:  # only a page that loaded uses up the field's own budget; a 404 moves to the next listed page
            used[entry["field"]] = used.get(entry["field"], 0) + 1
            fields = merge(fields, read(page["text"], url), url, evidence)
    return {"ok": True, "fields": fields, "evidence": evidence, "pages": pages, "extra_fetches_used": extra,
            "stop": stop}


# ---------- decisions in code ----------

def qualify(f, stop=""):
    """First match wins. Returns (verdict, rule, reason, flags)."""
    if f["certified"] == "yes":
        return "disqualified", "already certified", 'Site says: "%s"' % f["certified_quote"], []
    if f["b2b_saas"] == "no":
        return "disqualified", "not B2B SaaS", 'Site says: "%s"' % f["b2b_saas_quote"], []
    if f["b2b_saas"] != "yes":
        return "flagged", "unclear if B2B SaaS", "Could not tell who it sells to after reading its pages.", []
    small = f["funding_round"] in CONFIG["too_small"]["early_rounds"] or \
        0 < f["team_size"] < CONFIG["too_small"]["max_team_size"]
    if small and not f["enterprise_signal"]:
        quote = f["funding_round_quote"] if f["funding_round"] in CONFIG["too_small"]["early_rounds"] \
            else f["team_size_quote"]
        return "disqualified", "too small or too early", 'Site says: "%s", with no sign of enterprise selling' % quote, []
    flags = []
    if f["certified_in_progress"]:
        flags.append("certification in progress: may already use a competing tool")
    elif f["certified"] == "unknown":
        flags.append("no certification found on the pages read (treated as not certified)")
    if not _known(f["stage"]):
        flags.append("no growth or enterprise signal found: lower rank")
    if small:
        flags.append("small team, kept because it sells to enterprises")
    if stop.startswith("cap reached"):
        flags.append(stop)
    reason = 'B2B SaaS ("%s") with no certification shown' % f["b2b_saas_quote"]
    if _known(f["stage"]):
        reason += '; growth signal: "%s"' % f["stage_quote"]
    return "qualified", "B2B SaaS, not certified, big enough", reason, flags


def looks_large(f):
    big = CONFIG["large_company"]
    return f["funding_round"] in big["rounds"] or f["team_size"] >= big["min_team_size"]


def role_tier(position):
    text = (position or "").lower()
    for role in CONFIG["role_priority"]:
        if any(re.search(r"\b%s\b" % re.escape(k), text) for k in role["keywords"]):
            return role["tier"], role["label"]
    return None, None


def pick_contact(people, require_tier1=False):
    """Rank Hunter people by role priority, not seniority; ties go to higher confidence."""
    candidates = []
    for p in people:
        status = (p.get("verification") or {}).get("status")
        tier, label = role_tier(p.get("position"))
        if status == "invalid" or (p.get("confidence") or 0) < CONFIG["min_confidence"] or tier is None:
            continue  # untitled people cannot be ranked by role, so they are skipped
        candidates.append((tier, -(p.get("confidence") or 0), label, p))
    if require_tier1:  # at a large company only a security or compliance owner will do
        candidates = [c for c in candidates if c[0] == 1]
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


MAX_OTHERS = 8


def others_found(people, contact):
    """The other people Hunter returned with a usable address: shown on the company's people map, and markable as CC."""
    out = []
    for p in people:
        email = p.get("value")
        if not email or email == contact["email"] or (p.get("verification") or {}).get("status") == "invalid":
            continue
        out.append({"name": " ".join(filter(None, [p.get("first_name"), p.get("last_name")])) or email,
                    "position": p.get("position") or "", "email": email, "role_tier": role_tier(p.get("position"))[0]})
    return sorted(out, key=lambda o: o["role_tier"] or 9)[:MAX_OTHERS]


class HunterStop(RuntimeError):
    """Bad key or no searches left: asking again in this run cannot work."""


HUNTER_ATTEMPTS, HUNTER_WAIT = 3, 2.0


def hunter_people(domain):
    """One Hunter search per domain, reused for 7 days so a re-run never spends twice."""
    cached = store.STORE.get("cache", domain + "/hunter")
    if cached and time.time() - cached["saved"] < CACHE_DAYS * 86400:
        return cached["people"], False
    quota = checks.check_hunter()
    if not quota["ok"]:
        if "rejected the key" in quota["detail"]:
            raise HunterStop(quota["detail"])
        raise RuntimeError(quota["detail"])
    if quota["searches_left"] <= 0:
        raise HunterStop("Hunter has no searches left this month.")
    query = urllib.parse.urlencode({"domain": domain, "limit": 10, "required_field": "position",
                                    "seniority": "senior,executive", "api_key": os.environ["HUNTER_API_KEY"]})
    for attempt in range(1, HUNTER_ATTEMPTS + 1):
        try:
            # filtered searches can take Hunter well over 10 s
            people = checks.get_json("https://api.hunter.io/v2/domain-search?" + query, timeout=45)["data"].get("emails", [])
            break
        except urllib.error.HTTPError as e:  # no URL in any message: it holds the key
            if e.code in (401, 403):
                raise HunterStop("Hunter rejected the key (HTTP %d)." % e.code)
            if e.code == 429:
                raise HunterStop("Hunter says the search limit is used up (HTTP 429).")
            raise RuntimeError("Hunter search failed (HTTP %d)." % e.code)
        except Exception as e:
            if attempt == HUNTER_ATTEMPTS:
                raise RuntimeError("Hunter did not answer on %d tries (%s)." % (HUNTER_ATTEMPTS, type(e).__name__))
            time.sleep(HUNTER_WAIT * attempt)
    store.STORE.put("cache", domain + "/hunter", {"saved": time.time(), "people": people})
    return people, True


# ---------- writing and grading ----------

def write_draft(pack, model, corrections=""):
    user = "<pack>\n%s\n</pack>" % data(json.dumps(pack, indent=1))
    if corrections:  # the operator's own past edits, passed as data after the pack
        user += "\n" + corrections
    return ask_json(model, _prompt("write"), user, WRITE_SCHEMA, effort="high")


def subject_line(subject, company):
    """One line: a line break in a scraped company name would make Gmail refuse the whole message."""
    return " ".join(("[Draft] %s | %s" % (subject, company)).split())


def email_body(first_name, d):
    return "Hi %s,\n\n%s %s\n\n%s\n\n%s\n" % (first_name, d["hook"], d["pain"], d["value"], d["ask"])


def split_sentences(d):
    return [s for part in ("hook", "pain", "value", "ask")
            for s in re.split(r"(?<=[.!?])\s+", d[part].strip()) if s]


def banned_in(text):
    low = text.lower()
    return [b for b in CONFIG["banned_phrases"] if re.search(r"(?<!\w)%s(?!\w)" % re.escape(b.lower()), low)]


def check_draft(d, labels):
    """Code has the last word: banned list, length and the grader's labels decide ready or flagged."""
    trace = []
    for n, sentence in enumerate(split_sentences(d), 1):
        got = labels.get(n) or {"label": "MADE UP", "pack_field": "", "note": "the grader skipped this sentence"}
        entry = {"sentence": sentence, "label": got["label"], "pack_field": got["pack_field"], "note": got["note"]}
        hits = banned_in(sentence)
        if hits:
            entry.update(label="BANNED", note="uses: " + ", ".join(hits))
        trace.append(entry)
    counts = {key: sum(1 for t in trace if t["label"] == label)
              for key, label in (("from_pack", "FROM PACK"), ("generic", "GENERIC"),
                                 ("made_up", "MADE UP"), ("banned", "BANNED"))}
    problems = []
    if counts["made_up"]:
        problems.append("%d sentence(s) not backed by the facts" % counts["made_up"])
    if counts["banned"] or banned_in(d["subject"]):
        problems.append("banned wording")
    if trace and counts["generic"] / len(trace) > CONFIG["max_generic_share"]:
        problems.append("too generic (%d of %d sentences)" % (counts["generic"], len(trace)))
    words = len(" ".join(d[p] for p in ("hook", "pain", "value", "ask")).split())
    if words > CONFIG["max_words"]:
        problems.append("too long (%d words)" % words)
    if len(d["subject"].split()) > CONFIG["max_subject_words"]:
        problems.append("subject too long")
    if "—" in d["subject"] + d["hook"] + d["pain"] + d["value"] + d["ask"]:
        problems.append("em dash")
    return trace, counts, ("flagged" if problems else "ready"), problems


def grade(d, pack, style=()):
    numbered = "\n".join("%d. %s" % (n, s) for n, s in enumerate(split_sentences(d), 1))
    user = "<pack>\n%s\n</pack>\n<sentences>\n%s\n</sentences>" % (data(json.dumps(pack, indent=1)), data(numbered))
    if style:  # the operator's own rewrites: allowed phrasing, never facts
        user += "\n<operator_style>\n%s\n</operator_style>" % data("\n---\n".join(style))
    result = ask_json(HAIKU, _prompt("grade"), user, GRADE_SCHEMA, effort="medium")
    return check_draft(d, {x["n"]: x for x in result["labels"]})


def trace_line(c):
    total = sum(c.values())
    return "%d of %d sentences from the pack, %d generic, %d made up, %d banned" % (
        c["from_pack"], total, c["generic"], c["made_up"], c["banned"])


def cc_lines(record):
    """Who the operator marked as CC, and whether each was really emailed (only addresses on CC_ALLOWED are)."""
    review = record.get("review") or {}
    names = {o["email"]: o["name"] for o in record.get("others") or []}
    sent = set(review.get("cc_delivered") or [])
    return ["CC marked: %s <%s> (%s)" % (names.get(e, e), e, "emailed" if e in sent else "not emailed")
            for e in review.get("cc") or []]


def inbox_email(record):
    """The draft first, the reasoning directly under it."""
    r, c, d = record, record["contact"], record["draft"]
    sources = sorted({e["page_url"] for e in r["evidence"]})
    edited = (r.get("review") or {}).get("edited")  # what the operator changed it to, when he did
    lines = [edited["body"] if edited else email_body(c["first_name"], d), "-" * 40, "DRAFT ONLY. Nothing was sent to this person.",
             "Would go to: %s, %s <%s> (Hunter confidence %s, %s)" % (c["name"], c["position"], c["email"],
                                                                     c["confidence"], c["verification_status"]),
             *cc_lines(r),
             "", "Why this company: %s" % r["reason"], "Pages used: %s" % ", ".join(sources),
             "Why this person: %s" % c["why_this_person"],
             "Pain 1: %s [from %s]" % (d["pains"][0]["pain"], d["pains"][0]["evidence_field"]),
             "Pain 2: %s [from %s]" % (d["pains"][1]["pain"], d["pains"][1]["evidence_field"]),
             "This role is measured on: %s" % d["role_measured_on"],
             'Hook built from: "%s"' % r["fields"]["trigger_quote"], "Trace: %s" % trace_line(d["counts"])]
    if r["flags"]:
        lines.append("Flags: " + "; ".join(r["flags"]))
    lines += ["Writer model: %s" % d["model"], "Decision record: %s" % r["record_path"]]
    return "\n".join(lines)


# ---------- one company ----------

def run_company(domain, run_id, writer=SONNET, send=True, apply_corrections=True, halt=None):
    """`halt` is one dict per run, saved with the run between requests: the Hunter stop and the Claude spend so far."""
    halt = {} if halt is None else halt
    cost_at_start = claude.spent["usd"]
    key = "%s/%s" % (run_id, domain)
    record = {"domain": domain, "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
              "flags": [], "record_path": "runs/%s.json" % key}

    def done(verdict, reason, **extra):
        cost = round(claude.spent["usd"] - cost_at_start, 4)
        record.update(verdict=verdict, reason=reason, claude_cost_usd=cost, **extra)
        halt["spent"] = round(halt.get("spent", 0) + cost, 4)
        store.STORE.put("record", key, record)
        return record

    if halt.get("spent", 0) >= CONFIG["max_run_cost_usd"]:
        return done("flagged", "Not researched: this run reached its Claude cost cap of $%.2f."
                    % CONFIG["max_run_cost_usd"], rule_applied="cost cap")
    try:
        found = research(domain)
    except ClaudeError as e:
        return done("flagged", str(e), rule_applied="extraction failed")
    record["pages_fetched"] = found["pages"]
    if not found["ok"]:  # requirement 11: log the reason, move on, queue for a human
        return done("flagged", found["reason"], rule_applied="scrape failed", failure_reason=found["reason"])
    fields = found["fields"]
    record.update(name=fields["company_name"], fields=fields, evidence=found["evidence"],
                  extra_fetches_used=found["extra_fetches_used"], loop_stop=found["stop"])
    verdict, rule, reason, flags = qualify(fields, found["stop"])
    record.update(flags=flags, qualify_reason=reason)  # kept apart from the final reason, which may be a hold
    if verdict != "qualified":
        return done(verdict, reason, rule_applied=rule)  # disqualified or unclear: no Hunter, no email
    if not _known(fields["trigger"]):  # checked before Hunter so no search is spent on an email we cannot write
        return done("flagged", "CANNOT WRITE THIS EMAIL: no trigger found on %d page(s)." % len(found["pages"]),
                    rule_applied=rule, draft={"refusal": "missing field: trigger"})

    if halt.get("hunter"):  # no more Hunter calls for the rest of this run
        return done("flagged", "Qualified, but no contact was looked up: %s" % halt["hunter"], rule_applied=rule)
    try:
        people, spent = hunter_people(domain)
    except HunterStop as e:
        halt["hunter"] = str(e)
        return done("flagged", "Qualified, but no contact was looked up: %s" % e, rule_applied=rule)
    except RuntimeError as e:
        return done("flagged", str(e), rule_applied=rule)
    record["hunter_search_spent"] = spent
    large = looks_large(fields)
    contact, considered = pick_contact(people, require_tier1=large)
    record["candidates_considered"] = considered
    if not contact:
        why = "nobody in security, compliance or risk (required at a company this size)" if large else \
            "nobody with a ranked role, confidence %d+ and a deliverable email" % CONFIG["min_confidence"]
        return done("flagged", "No suitable contact: %s." % why, rule_applied=rule)
    record["contact"] = contact
    record["others"] = others_found(people, contact)

    pack = {"company": fields["company_name"], "what_it_does": fields["what_it_does"],
            "facts": {k: {"value": fields[k], "quote": fields[k + "_quote"],
                          "page": next((e["page_url"] for e in found["evidence"] if e["field"] == k), "")}
                      for k in ("b2b_saas", "stage", "trigger") if _known(fields[k])},
            "contact": {"first_name": contact["first_name"], "position": contact["position"],
                        "why_this_person": contact["why_this_person"]}}
    try:
        found = feedback.retrieve(contact["role_tier"], fields["funding_round"] if fields["funding_round"] != "unknown"
                                  else None) if apply_corrections else {"rows": [], "pattern": "", "error": "paused"}
        record["feedback_loop"] = {"corrections_used": [r["id"] for r in found["rows"]], "pattern": found["pattern"],
                                   "off_because": found["error"]}
        draft = write_draft(pack, writer, feedback.prompt_section(found))
    except ClaudeError as e:
        return done("flagged", str(e), rule_applied=rule)
    draft["model"] = writer
    if not draft["can_write"] or len(draft["pains"]) < 2:
        return done("flagged", "CANNOT WRITE THIS EMAIL: missing %s." % (draft["missing_field"] or "a usable fact"),
                    rule_applied=rule, draft=dict(draft, refusal=draft["missing_field"]), pack=pack)
    draft["body"] = email_body(contact["first_name"], draft)
    try:
        draft["trace"], draft["counts"], draft["grader_verdict"], problems = grade(
            draft, pack, [r["body_after"] for r in found["rows"]])
    except ClaudeError as e:
        return done("flagged", "Draft not checked: %s" % e, rule_applied=rule, draft=draft, pack=pack)
    record.update(rule_applied=rule, reason=reason, draft=draft, pack=pack)
    if problems:
        return done("flagged", "Draft held back: %s." % "; ".join(problems))
    if send:
        try:
            send_to_operator(subject_line(draft["subject"], fields["company_name"]), inbox_email(record))
            record["review"] = {"status": "Sent to me", "sent_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            record["review"] = {"status": "Qualified", "send_error": "Gmail send failed (%s)." % type(e).__name__}
    return done("qualified", reason)
