# DESIGN.md: Sprinto outbound agent
Chosen direction: C (Frost board), agreed 2026-11-17, replacing B (split desk, cream) from 2026-11-11. Feel: a Growth Lead opens this to see the whole week at a glance: how many domains went where, who was reached and why, then the drafts. It must read as a working dashboard, calm and dense, and make it impossible to confuse a flagged company with a ready one.

## Colour tokens (CSS variables)
--surface: #f7f9fa; --surface-2: #ecf0f2; --card: #ffffff; --text: #1f3038; --text-muted: #5d6b72;
--secondary: #1f3038; --accent: #0d7480; --on-accent: #ffffff; --accent-text: #0d7480;
--success: #1d5a33; --success-bg: #dcefe2;
--warning: #6b4a00; --warning-bg: #f6e7bd;
--danger: #8a2a1c; --danger-bg: #f6dcd6;
--info: #2f4a5a; --info-bg: #e2eaee;
--border: #dbe2e6; --bar: #9fb4bd;
Roles: 60% surface (cool white page, white cards), 30% secondary (dark slate: text, selected borders, the hover fill on buttons), 10% accent (teal).
Accent only on: the primary button ("Send to my inbox", "Open for manual review"), the one number that matters (the "need you" count), and the border of the To person on the people map. Never on body text.
Contrast checked: text on surface 12.9:1; text-muted on surface 5.2:1, on card 5.5:1, on surface-2 4.8:1; on-accent on accent 5.5:1; accent on card 5.5:1; status pairs: success 6.8:1, warning 6.6:1, danger 6.6:1, info 7.7:1.

## Type
Headings and body: Instrument Sans, weights 400 and 600. Numbers and domains: DM Mono 400/500 with tabular figures.
Scale: 12 / 13 / 14 / 15 / 17 / 20 / 24 / 32. Email body 17 px; evidence 14 px; labels 12 px uppercase with 0.04em tracking; dashboard numbers 32 px (24 px on phone).
Line length: 62ch maximum for email and evidence text.

## Layout and shape
Review is a dashboard, top to bottom: five number cards; the flow, full width; the org charts, full width; then the company groups as dropdowns; then the selected company end to end across the page. Single column below 820 px; number cards go 5, then 3, then 2 across. Spacing scale: 4 / 8 / 12 / 16 / 24 / 32. Radius: 8 px everywhere. White cards with a 1 px border; no shadows except the primary button's pulse ring. Density: comfortable.
Breakpoints: phone < 640, tablet < 1024, desktop.
Within the detail, the draft is separated by a 2 px slate rule, not another box.
The email fields run the full width of the detail card; the reasoning under them is set in two columns.

## Screens
**1. Run.** Opened Monday morning to answer "which domains do I run this week?". Fields: domain box (paste 8-15), domain count, Hunter searches left this month (X of the plan total, read live; 50 on this account), cost estimate. Actions: Run, Clear. Empty: placeholder showing one example domain. Error: invalid domains listed inline with the reason. Phone: single column, Run button full width. Never hunt for: the Hunter quota.

**2. Review (first screen).** Opened when the run finishes, to answer "do I trust this company, this person and this email enough to send?".
- Header: "Run of N domains", run time, Hunter searches left, and three counts (need you, drafts ready, dropped).
- Number cards: need you, drafts ready, dropped, Hunter searches left, average disagreement. ("Sent to me" was removed as a card and a funnel bar on 2026-11-17; the status label on a sent draft now reads "Sent", and the note under the draft still says it went to the operator's inbox.)
- Flow "How the companies flowed" (replaced the funnel on 2026-11-17): six stages left to right with an arrow between each: Pasted, Pages read, Qualified, Person found, Draft ready, You reviewed. Each stage shows its count and one line on what passing it means; under it, "Stopped here" lists every company that stopped at that stage with its reason, and clicking one opens it below. The first stage reads Found for a run found by Hunter Discover. No feedback loop box: the operator had it removed on 2026-11-17; the loop's figure stays in the Average disagreement card and on each draft ("Written with N of your earlier corrections"). On a phone the stages stack with downward arrows.
- Company groups (Needs you, Drafts to review, Dropped with reason) are dropdowns. The group of the open company starts open; the others start closed.
- People map: inside a company, "People map" opens a drawn chart: the company at the top, a line to each person. The person the email is addressed to is marked To; the others Hunter found there can be ticked as CC. Each person opens into their address, why they were or were not picked, and a notes box that saves when you leave it. Clicking a person on the reach map opens their company with this map open.
- CC: ticked people go with the send. They are named in the email the operator receives; only an address on `CC_ALLOWED` is really emailed.
- Org charts "Who we reached, and why" (replaced the network on 2026-11-17, from org-chart practice rather than any outside picture): one map per company that has people, as a row with the company, its one-line reason, status and people count; clicking the row opens a top-down tree: company at the root, then teams (Leadership, Security & compliance, Engineering, Revenue, Operations, Other teams, Shared inboxes, from Hunter's department, a ranked title winning), then the people of each team stacked in a column with square elbow lines. Every card is the same size: name, title, one tag. The emailed person is filled teal with "To · tier N"; a CC is dashed teal; others are plain; a missing security owner is a dashed grey "Gap" card. Role tags follow a sales stakeholder map: Decision maker, Owns compliance, Influencer, Feels the pain. Clicking a person opens their company below with their notes box focused. A key above names the four marks. "Find everyone here" appears only for a company searched for senior people only (large companies) and says it uses 1 Hunter search. Companies with no person found get one line under the maps pointing to the flow. The chart scrolls sideways inside its card, never the page.
- Skipped automatically: in a found run, a company that ends without a draft (unreadable site, unclear buyer, no contact) is not the operator's job: it sits in a closed group at the bottom, counts under Dropped, and the run header says how many drafts it aims for and how many spare companies are left.
- Find companies now: a primary button beside the Review title asks Hunter Discover for the next batch (also run by the daily timer at 08:00 IST); a found run is titled "N companies found for you" and its first flow stage reads "Found". A refusal (no searches left, run unfinished) is shown in words under the title.
- Left list grouped as Needs you, Drafts to review, Dropped with reason. Each item: company, one-line why with source page, status chip.
- Detail on the right: company, domain, status; then the draft (subject, body) with Send to my inbox, I rewrote it, Skip; then evidence: why this company, why this person, two pains, what this role is measured on, trace line (N of M sentences from the pack, generic, made up, banned).
- Feedback loop (Phase 4): the draft's subject and body are editable in place, with an optional one-line "Why did you change it?" field under them. An edited draft that is sent becomes Rewritten automatically, so the "I rewrote it" button is only for edits made outside the app. The header gains one more figure: average disagreement over the last 10 drafts.
- Statuses: Qualified, Sent to me, Rewritten, Disqualified, Flagged. Each has an icon and a label; never colour alone.
- Flagged and refused companies show "No draft" with the reason and Open for manual review.
- Empty: "No run yet. Paste domains on the Run screen." Error: a failed company shows its reason in plain words ("site blocked automated access") and never an empty row. Phone: list becomes cards, the selected card expands in place with the email first.
- Never hunt for: the reasoning under the draft.

## Motion
1. A row arriving during a run: 200 ms fade plus 6 px rise. Reduced motion: appears instantly.
2. A status changing: 250 ms chip cross-fade plus a brief background tint on the row. Reduced motion: chip swaps instantly, tint holds for 1 s.
3. The detail panel opening: 180 ms fade. Reduced motion: appears instantly.
4. Dashboard arriving: number cards and panels rise 10 px over 400 ms, staggered 60 ms; a number that changes counts to its new value in 500 ms; a funnel bar that changes grows from the left in 600 ms; a new person on the map rises in. Movement only, never a fade, so text keeps its contrast the whole time. Reduced motion: everything is in place at once.
6. Org chart: a map the operator opens grows in once, branch by branch (320 ms, team and people rows 80 ms apart, movement only); person cards lift 2 px on hover. Reduced motion: shown in place.
5. Buttons: on hover or keyboard focus a slate fill sweeps in from the left (250 ms) and the label turns white; pressing scales to 97%. The primary button pulses a teal ring three times when it appears, then rests. Map cards lift 2 px on hover. Reduced motion: colours change without movement, no pulse.
All plain CSS plus one small counter in `review.js`: no library, no licence or attribution. Wrap in `@media (prefers-reduced-motion: no-preference)`.

## Do / Don't
- Do lead the detail with the email, with its reasoning directly under or beside it.
- Do keep flagged companies in their own group at the top.
- Do show disqualified rows with their one-line reason; never hide them.
- Do set numbers, domains and source paths in the mono face, right-aligned in data views.
- Don't use the accent for anything except the primary button, the key count and the last funnel bar.
- Don't use emoji as icons: one icon set, 1.75 stroke, throughout.
- No default purple or indigo gradients, no glassmorphism or glow.
- No hero-plus-three-feature-cards template.
- No lorem ipsum, "John Doe" or round fake numbers: sample data looks like real company data.
- Status is never colour alone: add a label or icon.
- One radius, one spacing scale; no one-off values.
- No thick coloured stripe down one side of a card; show emphasis with a label, icon, tint or weight.
- No gradient text; no marketing buzzwords ("revolutionise", "supercharge", "seamless", "cutting-edge").
- Avoid Inter, Roboto, Geist, Plus Jakarta Sans, Space Grotesk and Fraunces. This direction uses Instrument Sans on purpose.
- Text left-aligned in data views; numbers right-aligned with tabular figures.
- Headings never skip a level (h1, then h2, then h3).
- The Impeccable detector (`npx impeccable detect <url>`) must come back clean before a phase is called done.
- Accepted detector finding: `overused-font` (Instrument Sans). It came with Direction C, which the operator chose from three rendered options on 2026-11-17, so this finding is expected and is not fixed.
