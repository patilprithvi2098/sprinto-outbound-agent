"""Finds companies for Sprinto on its own, so the operator never has to paste domains.
Hunter Discover (free: it spends no Hunter searches) lists B2B SaaS companies by size and country; companies
already researched in any run are skipped; the rest start a run like a pasted list would."""
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import date

import checks
import runs
import store
from domains import parse_domains
from pipeline import CONFIG

CFG = CONFIG["discover"]
CALLS = 4  # at most this many Discover calls per batch: each returns up to 100 companies
STEP_BUDGET = 150  # seconds: no new company is started after this, so a step finishes inside Vercel's 300 s
WORK_BUDGET = 120  # one hop of the server-side chain


def _ask(country, headcount):
    """One Discover call. The free plan has no paging, so variety comes from rotating country and size band."""
    body = {"industry": {"include": CFG["industry"]}, "keywords": {"include": CFG["keywords"], "match": "all"}, "headcount": [headcount],
            "headquarters_location": {"include": [{"country": country}]}, "limit": 100}
    request = urllib.request.Request("https://api.hunter.io/v2/discover?api_key=" + os.environ["HUNTER_API_KEY"],
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response).get("data") or []
    except urllib.error.HTTPError as e:  # no URL in the message: it holds the key
        if e.code == 403:
            raise RuntimeError("Hunter refused Discover (HTTP 403): this plan may not include it.")
        raise RuntimeError("Hunter Discover failed (HTTP %d)." % e.code)


def find(limit, today=None):
    """Up to `limit` new domains, never one researched before. Hunter must know at least one person there."""
    if not os.environ.get("HUNTER_API_KEY"):
        raise RuntimeError("HUNTER_API_KEY is not set.")
    seen = {r.get("domain") for r in store.STORE.records()}
    combos = [(c, h) for c in CFG["countries"] for h in CFG["headcount"]]
    start = (today or date.today()).toordinal() % len(combos)  # a different list each day
    picked = []
    for i in range(min(CALLS, len(combos))):
        country, headcount = combos[(start + i) % len(combos)]
        for c in _ask(country, headcount):
            d = (c.get("domain") or "").lower()
            if d and d not in seen and (c.get("emails_count") or {}).get("personal", 0) > 0:
                seen.add(d)
                picked.append(d)
        if len(picked) >= limit:
            break
    return parse_domains("\n".join(picked[:limit]))["valid"]  # the same checks a pasted list gets


def batch_size():
    """The daily batch, cut to the Hunter searches left: each qualified company spends one."""
    quota = checks.check_hunter()
    if not quota["ok"]:
        raise RuntimeError(quota["detail"])
    return min(CFG["batch"], quota["searches_left"])


def start_found():
    """Find companies and start a run on them. Returns (run_id, domains, None) or (None, [], message)."""
    last = runs.latest()
    if last and not last.get("finished_at"):
        return None, [], "The last run is still being researched. Open Review to let it finish."
    size = batch_size()
    if size <= 0:
        return None, [], "Hunter has no searches left this month, so no companies were looked for."
    # some companies always fall out (blocked site, certified, no contact), so spares wait in a queue and step in
    found = find(size * CFG["candidates_per_draft"])
    if not found:
        return None, [], "Hunter Discover found no companies that have not been researched already."
    domains = found[:size]
    run_id, _ = runs.start(domains, source="found", queue=found[size:], target=size)
    return run_id, domains, None


def cron_allowed(header):
    """Vercel sends `Authorization: Bearer <CRON_SECRET>`. Without the secret set, the timer cannot start anything."""
    secret = os.environ.get("CRON_SECRET")
    return bool(secret) and hmac.compare_digest((header or "").encode(), ("Bearer " + secret).encode())


def research(run_id, budget=STEP_BUDGET):
    """Research companies of one run until it is done or the time budget is spent. Returns the run state."""
    t0, state = time.time(), runs.state(run_id)
    done = lambda st: sum(1 for r in st["records"] if not r.get("pending"))  # spares can be added, so count finished ones
    while not state.get("finished_at") and time.time() - t0 < budget:
        before = done(state)
        state, _ = runs.step(run_id)
        if done(state) == before:  # every company left is being researched by another request
            break
    return state


def kick(run_id, host):
    """Keep a run going on the server with nobody on the page. On Vercel a request ends when it answers, so each
    work request researches for a while, then sends the next one to itself (signed with CRON_SECRET) and lets go.
    Locally the server lives on, so a thread does it. Returns False when it cannot (no CRON_SECRET on Vercel)."""
    local = not os.environ.get("VERCEL")
    secret = os.environ.get("CRON_SECRET")
    if not local and (not secret or not host):
        return False
    runs.mark_background(run_id)  # before the work starts, so this write never races the work's own writes to the run
    if local:
        threading.Thread(target=research, args=(run_id, 3600), daemon=True).start()
        return True
    request = urllib.request.Request("https://%s/api/work" % host, data=json.dumps({"run_id": run_id}).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + secret})
    try:
        urllib.request.urlopen(request, timeout=3)
    except Exception:  # expected: the next request carries on by itself after we stop waiting for its answer
        pass
    return True


def work(run_id, host):
    """One hop of the server-side chain."""
    state = research(run_id, budget=WORK_BUDGET)
    if not state.get("finished_at"):
        kick(run_id, host)
    return {"ok": True, "finished": bool(state.get("finished_at"))}


def daily(host=None):
    """The timer's job: finish an unfinished run, or find today's companies, then hand the research to the chain."""
    last = runs.latest()
    if last and not last.get("finished_at"):
        run_id, note = last["id"], "continued the unfinished run"
    else:
        run_id, domains, error = start_found()
        if error:
            return {"ok": False, "detail": error}
        note = "found %d companies" % len(domains)
    state = research(run_id)
    if not state.get("finished_at"):
        kick(run_id, host)
    left = sum(1 for r in state["records"] if r.get("pending"))
    return {"ok": True, "run_id": run_id, "detail": note + (", %d still to research" % left if left else ", all researched")}
