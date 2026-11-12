# Brief: Sprinto outbound agent (MESA Term 2, Case 2: Cold Outreach, at Scale)

## Stage 0: coverage map (agreed)
Problem: Sprinto's Growth Lead researches and writes 8-15 cold emails a week at 15-20 min each; quality drops by the end of the list because he is tired, not because the later companies are worse fits.
Core verb: judge whether a company is worth emailing, then personalise.
Primary user: the Growth Lead. He pastes a list of domains, leaves, and returns to drafts in his inbox with the reasoning behind each.
Working means: (1) a personalised email lands in his inbox, addressed to a named person, with a specific hook; (2) he can explain why the system picked this company, this person and this hook.

| Brief says | Build covers it | Status |
|---|---|---|
| Identify the right-fit companies | Scrape the company's own pages; disqualify if already certified, not B2B SaaS, or too early; qualify if B2B SaaS, no badge, growing or selling to enterprises | Covered |
| Agent loop to fetch more information | Model fills named fields; code checks empty ones; fetch the page where the fact lives; stop at 4 extra fetches and flag for a human | Covered |
| Find the right decision-maker | Hunter API, only after qualification; person chosen by role priority | Covered (thin: priority list and "too small" threshold are defaults to confirm) |
| Two most likely pain points | Two pains from company evidence and the person's role | Covered |
| Personalised email by name with a hook | Writer uses only filled pack fields; grader traces every sentence | Covered |
| Send via Gmail (hardcode to: own address) | Gmail API, own address only | Covered |
| Defend every decision | One JSON decision record per company | Covered |
| Follow-ups, replies, calendar booking, CRM, win/loss | Not in the brief | Excluded (next version) |
| Feedback loop (from class L5; not in the brief) | Added by the user on 2026-11-12, reversing the earlier exclusion: corrections he makes to drafts are stored in Neon Postgres and fed into later drafts | Covered (Phase 4) |

## Nine Checks verdict
Build, with a human at the send step. 01 YES, 02 YES, 03 UNCERTAIN (resolved by the Phase 0 feasibility test), 04 YES, 05 YES, 08 YES, 06 YES (to own inbox), 07 YES, 09 YES. Killed: full autonomy (check 07) and LinkedIn research of the person (check 03 and L4 login-wall rule). Open: Sprinto's current reply-rate baseline is unmeasured.

## Five Pre-Build Decisions
- Outcome: the Growth Lead gets more conversations with buyers who need certification and spends his week on them. Metric: time per company from 15-20 min to under 2 min while rewrites stay under 20%; reply rate logged from day one (baseline unmeasured).
- Baseline: 15-20 min per company (find about 3, research about 7, contact about 3, write about 5: estimates); 8-15 companies a week; about 2-5 hours a week; quality drops late in the list.
- Workflow change: he pastes domains; the system does the research, qualification, contact, pains and draft; he reviews every draft and its record before any real send; flagged companies come to him.
- Measurement: week 1 field-fill rate and Hunter usable-contact rate; week 4 time per company and rewrite rate; guardrail false qualifies and false disqualifies sampled weekly, plus cost per company; end-goal reply rate and meetings per 100 emails.
- Kill: rewrites over 50%, contact accuracy under 60%, running takes longer than manual, or false qualifies over 30% of a sampled week. Fallback: manual process. Decider: the Growth Lead.

## Build Requirements Brief (approved)
1. Disqualify on a certification badge (SOC 2, ISO 27001): `certified = yes` means disqualify and stop; no more fetches, no Hunter, no email.
2. Qualify on B2B SaaS, no badge, and growing or selling to enterprises (stage from funding, headcount, open roles, enterprise pricing tier). Too small or too early: disqualify, or low rank and flag.
3. Capped agent loop: model fills `certified`, `b2b_saas`, `stage` (and `trigger`); code checks for empty fields; fetch the page where that fact lives; stop when filled or after 4 extra fetches, then flag for a human.
4. Evidence-backed decision per company: verdict, facts found, source page, ICP rule applied.
5. Hunter after qualification only; the 25 searches a month are for qualified companies.
6. Pick the person by role priority, not seniority; record why.
7. Two specific pain points from the company's own public signal and the person's role.
8. Personalised email by name: observed signal, likely problem, reason to talk, CTA; art-of-selling rules in the prompt.
9. Send via Gmail to the operator's own address only; decision record is a separate file per company.
10. A human reviews every draft before any real send.
11. Scraper failures: log the reason, move to the next company, queue for human review.
12. Feedback loop (added 2026-11-12): when the Growth Lead edits or rejects a draft on the Review screen, store the before, the after and the context (role, role tier, company stage, sector, trigger) in the Neon `corrections` table; before writing a new draft, retrieve his most relevant past corrections and add them to the writer's prompt. Track the disagreement score over time.

Exclusions: follow-ups, reply handling, calendar booking, CRM updates; fully autonomous sending (check 07); LinkedIn and third-party review research (scope and legal exposure).
Judged by: Test 1 (email lands) via 5, 6, 7, 8, 9; Test 2 (defensible) via 1, 2, 3, 4, 6, 7, 8.
First result to show: the finished email with its reasoning directly under it, then drill back through the evidence.
