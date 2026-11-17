"""Finds companies for Sprinto on its own, so the operator never has to paste domains.
Hunter Discover (free: it spends no Hunter searches) lists B2B SaaS companies by size and country; companies
already researched in any run are skipped; the rest start a run like a pasted list would."""
import hmac
import json
import os
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


def _ask(country, headcount):
    """One Discover call. The free plan has no paging, so variety comes from rotating country and size band."""
    body = {"keywords": {"include": CFG["keywords"], "match": "all"}, "headcount": [headcount],
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
    domains = find(size)
    if not domains:
        return None, [], "Hunter Discover found no companies that have not been researched already."
    run_id, _ = runs.start(domains, source="found")
    return run_id, domains, None


def cron_allowed(header):
    """Vercel sends `Authorization: Bearer <CRON_SECRET>`. Without the secret set, the timer cannot start anything."""
    secret = os.environ.get("CRON_SECRET")
    return bool(secret) and hmac.compare_digest((header or "").encode(), ("Bearer " + secret).encode())


def daily():
    """The timer's job: finish an unfinished run, or find today's companies; then research until the time budget."""
    t0 = time.time()
    last = runs.latest()
    if last and not last.get("finished_at"):
        run_id, note = last["id"], "continued the unfinished run"
    else:
        run_id, domains, error = start_found()
        if error:
            return {"ok": False, "detail": error}
        note = "found %d companies" % len(domains)
    state = runs.state(run_id)
    pending = lambda st: sum(1 for r in st["records"] if r.get("pending"))
    while not state.get("finished_at") and time.time() - t0 < STEP_BUDGET:
        before = pending(state)
        state, _ = runs.step(run_id)
        if pending(state) == before:  # every company left is being researched by another request
            break
    left = pending(state)
    return {"ok": True, "run_id": run_id, "detail": note + (", %d still to research (Review finishes them)" % left if left else ", all researched")}
