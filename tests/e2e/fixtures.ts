// A finished run shaped like real decision records. Company and person details are invented.
const ev = (field: string, quote: string, path: string, host: string) => ({ field, quote, page_url: `https://${host}${path}` });

export const READY = {
  domain: "kestrelmetrics.io", name: "Kestrel Metrics", verdict: "qualified", status: "Qualified",
  reason: 'B2B SaaS ("Usage analytics for product teams") with no certification shown; growth signal: "Series B led by Northzone"',
  qualify_reason: 'B2B SaaS ("Usage analytics for product teams") with no certification shown; growth signal: "Series B led by Northzone"',
  rule_applied: "B2B SaaS, not certified, big enough",
  flags: ["no certification found on the pages read (treated as not certified)"],
  evidence: [ev("b2b_saas", "Usage analytics for product teams", "/", "kestrelmetrics.io"),
    ev("stage", "Series B led by Northzone", "/careers", "kestrelmetrics.io"),
    ev("trigger", "Kestrel opens its Frankfurt data region", "/blog", "kestrelmetrics.io")],
  pages_fetched: [{ url: "https://kestrelmetrics.io/", ok: true, reason: "" }],
  fields: { trigger_quote: "Kestrel opens its Frankfurt data region" },
  others: [{ name: "Omar Reyes", position: "CTO", email: "omar@kestrelmetrics.io", role_tier: 2 }],
  contact: { name: "Ines Albrecht", first_name: "Ines", position: "Head of Security", email: "ines@kestrelmetrics.io", confidence: 91,
    verification_status: "valid", role_tier: 1, why_this_person: "Highest on the role priority list (tier 1, security, compliance or risk) among 3 usable of 9 people Hunter found." },
  draft: {
    subject: "Frankfurt region and security reviews", grader_verdict: "ready", model: "claude-sonnet-5-5",
    body: "Hi Ines,\n\nKestrel's new Frankfurt data region will bring in EU buyers who ask for ISO 27001. Those questionnaires usually land on security first.\n\nSprinto automates SOC 2, ISO 27001 and GDPR compliance for SaaS companies, so evidence stops being a manual job.\n\nIs ISO 27001 already on your plan for next year?\n",
    pains: [{ pain: "EU buyers in the new region will send security questionnaires.", evidence_field: "facts.trigger" },
      { pain: "Series B growth means more enterprise reviews landing on one team.", evidence_field: "facts.stage" }],
    role_measured_on: "Passing customer security reviews without slowing deals",
    counts: { from_pack: 4, generic: 0, made_up: 0, banned: 0 },
    trace: [{ sentence: "Kestrel's new Frankfurt data region will bring in EU buyers who ask for ISO 27001.", label: "FROM PACK", pack_field: "facts.trigger", note: "" }],
  },
  review: { status: "Qualified" },
};

export const FLAGGED = {
  domain: "tallybook.co", name: "Tallybook", verdict: "flagged", status: "Flagged",
  reason: "CANNOT WRITE THIS EMAIL: no trigger found on 5 page(s). <img src=x onerror=alert(1)>",
  flags: ["cap reached (4 extra pages) with trigger still unknown"],
  evidence: [ev("b2b_saas", "Bookkeeping software for agencies", "/", "tallybook.co")],
  pages_fetched: [{ url: "https://tallybook.co/", ok: true, reason: "" }], fields: { trigger_quote: "" },
};

export const BLOCKED = {
  domain: "orbitly.app", verdict: "flagged", status: "Flagged", flags: [],
  reason: "site blocked automated access (HTTP 403)", pages_fetched: [{ url: "https://orbitly.app/", ok: false, reason: "site blocked automated access (HTTP 403)" }],
};

export const DROPPED = {
  domain: "fernpay.com", name: "Fernpay", verdict: "disqualified", status: "Disqualified", flags: [],
  reason: 'Site says: "Fernpay is SOC 2 Type II certified"',
  evidence: [ev("certified", "Fernpay is SOC 2 Type II certified", "/security", "fernpay.com")],
  pages_fetched: [{ url: "https://fernpay.com/", ok: true, reason: "" }],
};

export const run = (records: object[], extra: object = {}) => ({
  run: { id: "20261112-130000", started_at: "2026-11-12T07:30:00+00:00", finished_at: "2026-11-12T07:36:41+00:00",
    domains: records.map((r: any) => r.domain), records, hunter_searches_used: 1, ...extra },
});
