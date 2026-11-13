# Sprinto outbound agent

A research-and-draft tool for cold outreach, built for MESA PGP Term 2, Case 2 ("Cold Outreach, at Scale").

The Growth Lead pastes 8–15 company domains. For each company the app:
1. reads the company's own pages
2. decides in code whether the company is worth emailing (not already SOC 2 / ISO 27001 certified, B2B SaaS, big enough)
3. looks up the right person with Hunter
4. has Claude write a short personalised email
5. checks every sentence against the evidence

The operator reviews each draft and its reasoning before anything is sent. Drafts only ever go to the operator's own inbox. Edits the operator makes are stored and fed back into later drafts.

## How it works

| Step | Where |
|---|---|
| Domain list checks | `app/domains.py` |
| Fetch the company's pages (public addresses only, robots.txt respected, HTTPS-only redirects) | `app/scrape.py` |
| Research loop: extract facts with quotes from the page, fetch the page where a missing fact lives, at most 4 extra pages | `app/pipeline.py`, `prompts/extract.md`, `config/icp.json` |
| Qualify, pick the contact by role priority | `app/pipeline.py` |
| Write and grade the draft | `prompts/write.md`, `prompts/grade.md` |
| Review screen, send to own inbox, feedback loop | `web/`, `app/runs.py`, `app/mailer.py`, `app/feedback.py` |
| Storage: files locally, Neon Postgres on Vercel | `app/store.py`, `db/schema.sql` |

The plan, decisions and test log are in `docs/mesa/`, and the design system is in `DESIGN.md`.

## Run it locally

Python 3.9+ is required.

```bash
python3 -m pip install --user -r requirements.txt
cp .env.example .env    # then fill in the values
python3 app/server.py   # http://127.0.0.1:8321
```

Without `APP_PASSWORD`, the local app is open on 127.0.0.1 only. A terminal run is also available: `python3 run.py dub.co plausible.io`.

## Deploy on Vercel

1. Import this repository in Vercel. No build settings are needed; `vercel.json` has them.
2. In Project Settings → Environment Variables, add every variable from `.env.example`:
   - `ANTHROPIC_API_KEY`
   - `HUNTER_API_KEY`
   - `OPERATOR_EMAIL`
   - `GMAIL_SENDER`
   - `GMAIL_APP_PASSWORD`
   - `DATABASE_URL`
   - `APP_PASSWORD`: a password you choose and share with whoever should use the site
3. Create the tables once in your Neon database (`db/schema.sql`).
4. Deploy.

On Vercel, each company is researched in its own request, within the 5-minute function limit. The Review page drives the run, so keep it open while a run is going.

## Tests

```bash
python3 -m unittest discover -s tests   # unit tests; network, email and database are stubbed
npx playwright test                     # browser tests in installed Chrome, every paid or sending call stubbed
```

## Safety choices

- **Emails go only to `OPERATOR_EMAIL`.** No request can change the recipient.
- **Secrets stay in environment variables** and never appear in errors, records or git.
- **Requests from other sites are refused:**
  - The local server rejects requests addressed to other hostnames (DNS rebinding).
  - It also rejects other origins.
  - Pages cannot be framed.
- **Scraped text is treated as data:**
  - Every extracted fact needs a quote that appears on the page.
  - The model's output never chooses a URL, a file, a recipient or a query.
- **No headless browser is run** on scraped sites.
