# DESIGN.md: Sprinto outbound agent
Chosen direction: B (split desk), agreed 2026-11-11. Feel: A Growth Lead checks this between calls. It must feel calm and dense, read like a clean worksheet, and make it impossible to confuse a flagged company with a ready one. Nothing playful.

## Colour tokens (CSS variables)
--surface: #F3EEE3; --surface-2: #EAE3D3; --text: #111111; --text-muted: #5a5448;
--secondary: #111111; --accent: #E2622A; --on-accent: #111111; --accent-text: #9a3d12;
--success: #2d5a1f; --success-bg: #dde8d3;
--warning: #6e4800; --warning-bg: #f2e2b8;
--danger: #8e2f12; --danger-bg: #f1d6cb;
--info: #3b4a52; --info-bg: #e0e2dc;
--border: #d6cdb8;
Roles: 60% surface (cream), 30% secondary (ink: header rule, headings, selected-row border), 10% accent (burnt orange).
Accent only on: the primary button ("Send to my inbox", "Open for manual review") and the one number that matters (the "need you" count, set in --accent-text). Never on body text.
Contrast checked: text on surface 16.3:1; text-muted on surface 6.5:1; text-muted on surface-2 5.9:1; text on surface-2 14.8:1; on-accent on accent 5.4:1; accent-text on surface 6.0:1; accent on surface 3.0:1 (icons and large shapes only, never small text); status pairs: success 6.4:1, warning 6.3:1, danger 5.9:1, info 7.0:1.

## Type
Headings: Familjen Grotesk, weights 400 and 600. Body: Familjen Grotesk 400. Numbers and domains: IBM Plex Mono 400/500 with tabular figures.
Scale: 12 / 13 / 14 / 15 / 17 / 20 / 24 / 32. Email body 17 px; evidence 14 px; labels 12 px uppercase with 0.04em tracking.
Line length: 62ch maximum for email and evidence text.

## Layout and shape
Grid: two columns on desktop (list about 1fr, detail about 2fr); single column below 820 px. Spacing scale: 4 / 8 / 12 / 16 / 24 / 32. Radius: 10 px everywhere. Borders over shadows; no shadows. Density: comfortable.
Breakpoints: phone < 640, tablet < 1024, desktop.
Within the detail, no card inside a card: the draft is separated by a 2 px ink rule, not a box.

## Screens
**1. Run.** Opened Monday morning to answer "which domains do I run this week?". Fields: domain box (paste 8-15), domain count, Hunter searches left this month (X of 25), cost estimate. Actions: Run, Clear. Empty: placeholder showing one example domain. Error: invalid domains listed inline with the reason. Phone: single column, Run button full width. Never hunt for: the Hunter quota.

**2. Review (first screen).** Opened when the run finishes, to answer "do I trust this company, this person and this email enough to send?".
- Header: "Run of N domains", run time, Hunter searches left, and three counts (need you, drafts ready, dropped).
- Left list grouped as Needs you, Drafts to review, Dropped with reason. Each item: company, one-line why with source page, status chip.
- Detail on the right: company, domain, status; then the draft (subject, body) with Send to my inbox, I rewrote it, Skip; then evidence: why this company, why this person, two pains, what this role is measured on, trace line (N of M sentences from the pack, generic, made up, banned).
- Statuses: Qualified, Sent to me, Rewritten, Disqualified, Flagged. Each has an icon and a label; never colour alone.
- Flagged and refused companies show "No draft" with the reason and Open for manual review.
- Empty: "No run yet. Paste domains on the Run screen." Error: a failed company shows its reason in plain words ("site blocked automated access") and never an empty row. Phone: list becomes cards, the selected card expands in place with the email first.
- Never hunt for: the reasoning under the draft.

## Motion
1. A row arriving during a run: 200 ms fade plus 6 px rise. Reduced motion: appears instantly.
2. A status changing (for example Qualified to Sent to me): 250 ms chip cross-fade plus a brief background tint on the row. Reduced motion: chip swaps instantly, tint holds for 1 s.
3. The detail panel opening: 180 ms fade. Reduced motion: appears instantly.
All three are plain CSS: no library, no licence or attribution. Wrap in `@media (prefers-reduced-motion: no-preference)`.

## Do / Don't
- Do lead the detail with the email, with its reasoning directly under or beside it.
- Do keep flagged companies in their own group at the top.
- Do show disqualified rows with their one-line reason; never hide them.
- Do set numbers, domains and source paths in the mono face, right-aligned in data views.
- Don't use the accent for anything except the primary button and the key count.
- Don't use emoji as icons: one icon set, 1.75 stroke, throughout.
- No default purple or indigo gradients, no glassmorphism or glow.
- No hero-plus-three-feature-cards template.
- No lorem ipsum, "John Doe" or round fake numbers: sample data looks like real company data.
- Status is never colour alone: add a label or icon.
- One radius, one spacing scale; no one-off values.
- No thick coloured stripe down one side of a card; show emphasis with a label, icon, tint or weight.
- No gradient text; no marketing buzzwords ("revolutionise", "supercharge", "seamless", "cutting-edge").
- Avoid Inter, Roboto, Geist, Plus Jakarta Sans, Space Grotesk and Fraunces. This direction uses Familjen Grotesk on purpose.
- Text left-aligned in data views; numbers right-aligned with tabular figures.
- Headings never skip a level (h1, then h2, then h3).
- The Impeccable detector (`npx impeccable detect <url>`) must come back clean before a phase is called done.
- Accepted detector finding: `cream-palette` on the page background. The cream surface is the user's own saved palette (Startup Warm) and was chosen on purpose as Direction B from three rendered options, so this finding is expected and is not fixed.
