import { test, expect, type Page } from "@playwright/test";
import { guardDialogs, hasHorizontalOverflow, tabUntil } from "./helpers";
import { READY, FLAGGED, BLOCKED, DROPPED, run } from "./fixtures";

// Every API is stubbed: /api/action would send real email, /api/quota calls Hunter.
let loopState: object = { ok: true, stored: 3, drafts_counted: 4, avg_disagreement: 0.25 };
test.beforeEach(() => { loopState = { ok: true, stored: 3, drafts_counted: 4, avg_disagreement: 0.25 }; });

async function open(page: Page, payload: object | object[] = run([FLAGGED, BLOCKED, READY, DROPPED])) {
  guardDialogs(page);
  const responses = Array.isArray(payload) ? payload : [payload];
  let n = 0;
  await page.route("**/api/runs/latest", (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(responses[Math.min(n++, responses.length - 1)]) }));
  await page.route("**/api/quota", (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, searches_left: 43, searches_total: 50 }) }));
  await page.route("**/api/feedback", (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(loopState) }));
  await page.goto("/review.html");
}

const bodies: any[] = [];
function stubAction(page: Page, reply: (action: string) => { status: number; body: object }, delayMs = 0) {
  const calls: string[] = [];
  bodies.length = 0;
  return page.route("**/api/action", async (route) => {
    const { action } = route.request().postDataJSON();
    calls.push(action);
    bodies.push(route.request().postDataJSON());
    if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
    const { status, body } = reply(action);
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  }).then(() => calls);
}

const item = (page: Page, name: string) => page.locator(".item").filter({ hasText: name });
const detail = (page: Page) => page.locator("#detail");
// Companies sit in dropdown groups; only the group of the open company starts open.
async function pick(page: Page, name: string) {
  const group = page.locator("details.group").filter({ has: item(page, name) });
  if ((await group.getAttribute("open")) === null) await group.locator("summary").click();
  await item(page, name).click();
}

test("empty state when there is no run yet", async ({ page }) => {
  await open(page, { run: null });
  await expect(page.getByRole("heading", { name: "No run yet" })).toBeVisible();
  await page.getByRole("link", { name: "Paste domains instead" }).click();
  await expect(page.getByRole("heading", { name: "Run", exact: true })).toBeVisible();
});

test("header counts and groups, with flagged companies first", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Run of 4 domains");
  await expect(page.locator("#c-need")).toHaveText("2");
  await expect(page.locator("#c-ready")).toHaveText("1");
  await expect(page.locator("#c-dropped")).toHaveText("1");
  await expect(page.locator("#c-hunter")).toHaveText("43 of 50");
  await expect(page.locator(".group")).toHaveText([/Needs you\s*2/, /Drafts to review\s*1/, /Dropped with reason\s*1/]);
  await expect(page.getByText("took 6 min 41 s")).toBeVisible();
});

test("every status has a text label, not just a colour", async ({ page }) => {
  await open(page);
  for (const g of ["Drafts to review", "Dropped with reason"]) await page.locator(`details[data-group="${g}"] > summary`).click();
  for (const s of ["Flagged", "Qualified", "Disqualified"]) await expect(page.locator(".list .chip", { hasText: s }).first()).toBeVisible();
});

test("a flagged company shows No draft, its reason as text, and Open for manual review", async ({ page }) => {
  await open(page);
  await expect(item(page, "Tallybook")).toHaveAttribute("aria-pressed", "true"); // first in Needs you is opened
  await expect(detail(page).getByRole("heading", { name: "No draft" })).toBeVisible();
  await expect(detail(page).getByText("<img src=x onerror=alert(1)>", { exact: false })).toBeVisible(); // shown, never run
  await expect(detail(page).getByRole("link", { name: "Open for manual review" })).toHaveAttribute("href", "https://tallybook.co/");
  await pick(page, "orbitly.app");
  await expect(detail(page).getByText("site blocked automated access (HTTP 403)")).toBeVisible();
});

test("a ready draft leads with the email and keeps the reasoning under it", async ({ page }) => {
  await open(page);
  await pick(page, "Kestrel Metrics");
  const d = detail(page);
  await expect(d.getByLabel("Subject")).toHaveValue("Frankfurt region and security reviews");
  await expect(d.getByLabel("Email", { exact: true })).toHaveValue(/^Hi Ines,/);
  await expect(d.getByText("Ines Albrecht, Head of Security")).toBeVisible();
  const order = await d.evaluate((el) => {
    const draft = el.querySelector(".draft")!, reasons = el.querySelector(".reasons")!;
    return draft.compareDocumentPosition(reasons) & Node.DOCUMENT_POSITION_FOLLOWING;
  });
  expect(order).toBeTruthy();
  for (const h of ["Why this company", "Why this person", "Two pains", "What this role is measured on"])
    await expect(d.getByRole("heading", { name: h })).toBeVisible();
  await expect(d.getByText("Trace: 4 of 4 sentences from the pack, 0 generic, 0 made up, 0 banned")).toBeVisible();
  await expect(d.locator(".src", { hasText: "/careers" })).toBeVisible();
});

test("Send to my inbox sends once on a double click and the status changes", async ({ page }) => {
  await open(page);
  const calls = await stubAction(page, () => ({ status: 200, body: { record: { ...READY, status: "Sent to me", review: { status: "Sent to me", sent_at: "2026-11-12T08:00:00+00:00" } } } }), 600);
  await pick(page, "Kestrel Metrics");
  const send = detail(page).getByRole("button", { name: "Send to my inbox" });
  await send.click();
  await expect(send).toBeDisabled();
  await send.click({ force: true });
  await expect(item(page, "Kestrel Metrics").locator(".chip")).toHaveText("Sent");
  await expect(detail(page).getByText(/Sent to your inbox/)).toBeVisible();
  await expect(detail(page).getByRole("button", { name: "Edit and send again" })).toBeVisible(); // sending again needs a change first
  expect(calls).toEqual(["send"]);
});

test("a failed send says so in plain words and can be retried", async ({ page }) => {
  await open(page);
  await stubAction(page, () => ({ status: 502, body: { error: "Gmail send failed (SMTPServerDisconnected). Try again." } }));
  await pick(page, "Kestrel Metrics");
  await detail(page).getByRole("button", { name: "Send to my inbox" }).click();
  await expect(detail(page).getByRole("alert")).toHaveText("Gmail send failed (SMTPServerDisconnected). Try again.");
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeEnabled();
});

test("I rewrote it marks the draft Rewritten; Skip disables sending", async ({ page }) => {
  await open(page);
  await stubAction(page, (a) => ({ status: 200, body: { record: a === "rewrote"
    ? { ...READY, status: "Rewritten", review: { status: "Rewritten", rewritten: true } }
    : { ...READY, review: { status: "Qualified", skipped: true } } } }));
  await pick(page, "Kestrel Metrics");
  await detail(page).getByRole("button", { name: "I rewrote it" }).click();
  await expect(item(page, "Kestrel Metrics").locator(".chip")).toHaveText("Rewritten");
  await detail(page).getByRole("button", { name: "Skip" }).click();
  await expect(detail(page).getByText("Skipped. Nothing will be sent.")).toBeVisible();
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeDisabled();
});

test("while a run is going, the page researches one company per request until done", async ({ page }) => {
  const pending = { domain: "fernpay.com", status: "Researching", pending: true };
  const steps: string[] = [];
  await page.route("**/api/step", async (route) => {
    steps.push(route.request().postDataJSON().run_id);
    await new Promise((r) => setTimeout(r, 400));
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(run([READY, DROPPED])) });
  });
  await open(page, run([READY, pending], { finished_at: null }));
  await expect(page.getByText(/Researching: 1 of 2 done/)).toBeVisible();
  await expect(item(page, "fernpay.com").locator(".chip")).toHaveText("Researching");
  await expect(item(page, "Fernpay").locator(".chip")).toHaveText("Disqualified", { timeout: 6000 });
  await expect(page.locator('li[data-domain="fernpay.com"]')).toHaveClass(/arrive/);
  expect(steps).toEqual(["20261112-130000"]); // one step, then the run reports finished and the page stops asking
});

test("if a research step fails, the page says so and tries again", async ({ page }) => {
  const pending = { domain: "fernpay.com", status: "Researching", pending: true };
  let calls = 0;
  await page.route("**/api/step", async (route) => {
    calls += 1;
    if (calls === 1) return route.abort();
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(run([READY, DROPPED])) });
  });
  await open(page, run([READY, pending], { finished_at: null }));
  await expect(page.getByText("Research paused: the app did not answer. It will try again in a few seconds.")).toBeVisible();
  await expect(item(page, "Fernpay").locator(".chip")).toHaveText("Disqualified", { timeout: 12000 });
  expect(calls).toBe(2);
});

test("an expired sign-in sends the operator to the sign-in page and back", async ({ page }) => {
  guardDialogs(page);
  await page.route("**/api/runs/latest", (r) => r.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: "Sign in", login: true }) }));
  await page.route("**/api/quota", (r) => r.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
  await page.route("**/api/feedback", (r) => r.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
  await page.goto("/review.html");
  await expect(page).toHaveURL(/login\.html\?next=review\.html$/);
});

test("server down shows a plain message", async ({ page }) => {
  guardDialogs(page);
  await page.route("**/api/runs/latest", (r) => r.abort());
  await page.route("**/api/quota", (r) => r.abort());
  await page.goto("/review.html");
  await expect(page.getByRole("alert")).toHaveText("The app is not responding. Check that the server is still running, then reload.");
});

test("keyboard only: move to a company and open it", async ({ page }) => {
  await open(page);
  expect(await tabUntil(page, 'details[data-group="Drafts to review"] > summary')).toBe(true);
  await page.keyboard.press("Enter"); // opens the dropdown group
  expect(await tabUntil(page, 'li[data-domain="kestrelmetrics.io"] .item')).toBe(true);
  await page.keyboard.press("Enter");
  await expect(detail(page).getByLabel("Subject")).toHaveValue("Frankfurt region and security reviews");
  expect(await tabUntil(page, "#ed-subject")).toBe(true);
  expect(await tabUntil(page, "#ed-body")).toBe(true);
  expect(await tabUntil(page, "#ed-reason")).toBe(true);
  expect(await tabUntil(page, '[data-act="send"]')).toBe(true);
});

test("layout: no sideways scroll; on a phone the selected card opens in place", async ({ page }, info) => {
  await open(page);
  await pick(page, "Kestrel Metrics");
  expect(await hasHorizontalOverflow(page)).toBe(false);
  const inCard = await page.locator('li[data-domain="kestrelmetrics.io"] #detail').count();
  expect(inCard).toBe(info.project.name === "chrome-375" ? 1 : 0);
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeVisible();
});

// ---------- Phase 4: the feedback loop ----------

const REWRITTEN = { ...READY, status: "Rewritten", review: { status: "Rewritten", rewritten: true, sent_at: "2026-11-12T08:00:00+00:00",
  disagreement: 0.21, changed_parts: ["ask"], correction: { saved: true, id: 12, note: null },
  edited: { subject: READY.draft.subject, body: READY.draft.body.replace("Is ISO 27001 already on your plan for next year?", "Worth a one-line reply?") } } };

test("an edited draft is sent as edited, with the reason, and becomes Rewritten", async ({ page }) => {
  await open(page);
  const calls = await stubAction(page, () => ({ status: 200, body: { record: REWRITTEN } }), 500);
  await pick(page, "Kestrel Metrics");
  const d = detail(page);
  const body = d.getByLabel("Email", { exact: true });
  await body.fill((await body.inputValue()).replace("Is ISO 27001 already on your plan for next year?", "Worth a one-line reply?"));
  await d.getByLabel("Why did you change it? (optional)").fill("Softer ask");
  const send = d.getByRole("button", { name: "Send to my inbox" });
  await send.click();
  await send.click({ force: true });
  await expect(item(page, "Kestrel Metrics").locator(".chip")).toHaveText("Rewritten");
  expect(calls).toEqual(["send"]);
  expect(bodies[0].body).toContain("Worth a one-line reply?");
  expect(bodies[0].reason).toBe("Softer ask");
  expect(bodies[0].subject).toBe("Frankfurt region and security reviews");
  await expect(d.getByText(/You changed: ask\. Saved to the feedback loop\./)).toBeVisible();
  await expect(d.getByLabel("Email", { exact: true })).toHaveValue(/Worth a one-line reply\?/); // what was sent stays on screen
  await expect(d.getByLabel("Email", { exact: true })).not.toBeEditable();
});

test("an empty subject or email is refused before anything is sent", async ({ page }) => {
  await open(page);
  const calls = await stubAction(page, () => ({ status: 200, body: { record: REWRITTEN } }));
  await pick(page, "Kestrel Metrics");
  const d = detail(page);
  await d.getByLabel("Email", { exact: true }).fill("   ");
  await d.getByRole("button", { name: "Send to my inbox" }).click();
  await expect(d.getByRole("alert")).toHaveText("The email needs a subject and a body.");
  await expect(d.getByLabel("Email", { exact: true })).toBeFocused();
  await d.getByLabel("Email", { exact: true }).fill("Hi Ines,\n\nShort note.");
  await d.getByLabel("Subject").fill("");
  await d.getByRole("button", { name: "Send to my inbox" }).click();
  await expect(d.getByLabel("Subject")).toBeFocused();
  expect(calls).toEqual([]);
});

test("very long edits are capped in the fields and never overflow the page", async ({ page }) => {
  await open(page);
  await pick(page, "Kestrel Metrics");
  const d = detail(page);
  await d.getByLabel("Subject").fill("s".repeat(400));
  await d.getByLabel("Email", { exact: true }).fill("b".repeat(6000));
  await d.getByLabel("Why did you change it? (optional)").fill("r".repeat(1200));
  expect((await d.getByLabel("Subject").inputValue()).length).toBe(200);
  expect((await d.getByLabel("Email", { exact: true }).inputValue()).length).toBe(5000);
  expect((await d.getByLabel("Why did you change it? (optional)").inputValue()).length).toBe(1000);
  expect(await hasHorizontalOverflow(page)).toBe(false);
});

test("a save that fails still sends, and says the correction was not stored", async ({ page }) => {
  await open(page);
  await stubAction(page, () => ({ status: 200, body: { record: { ...REWRITTEN, review: { ...REWRITTEN.review,
    correction: { saved: false, id: null, note: "the feedback database could not be reached (TimeoutError)" } } } } }));
  await pick(page, "Kestrel Metrics");
  await detail(page).getByLabel("Subject").fill("Frankfurt and ISO 27001");
  await detail(page).getByRole("button", { name: "Send to my inbox" }).click();
  await expect(detail(page).getByText(/Not saved to the feedback loop: the feedback database could not be reached/)).toBeVisible();
  await expect(item(page, "Kestrel Metrics").locator(".chip")).toHaveText("Rewritten");
});

test("Skip sends the reason along as a rejection", async ({ page }) => {
  await open(page);
  await stubAction(page, () => ({ status: 200, body: { record: { ...READY, review: { status: "Qualified", skipped: true, disagreement: 1 } } } }));
  await pick(page, "Kestrel Metrics");
  await detail(page).getByLabel("Why did you change it? (optional)").fill("Wrong person");
  await detail(page).getByRole("button", { name: "Skip" }).click();
  expect(bodies[0]).toMatchObject({ action: "skip", reason: "Wrong person" });
  expect(bodies[0].body).toBeUndefined();
});

test("header shows average disagreement, and says when the loop is off", async ({ page }) => {
  await open(page);
  await expect(page.locator("#c-disagree")).toHaveText("25%");
  await expect(page.getByText("last 4 drafts")).toBeVisible();
  await expect(page.locator("#loop-off")).toBeHidden();
  loopState = { ok: false, detail: "The feedback loop is off: the feedback database could not be reached (TimeoutError). Runs and sends still work.", drafts_counted: 0, avg_disagreement: null };
  await page.reload();
  await expect(page.getByRole("status")).toHaveText(/The feedback loop is off: .* Runs and sends still work\./);
  await expect(page.locator("#c-disagree")).toHaveText("-");
});

test("a draft written with earlier corrections says so, and a paused loop is explained", async ({ page }) => {
  const learned = { ...READY, feedback_loop: { corrections_used: [3, 9], pattern: "He rewrote the ask in 2 of his last 3 edits.", off_because: null } };
  await open(page, run([learned], { corrections_paused: true }));
  await expect(detail(page).getByText("Written with 2 of your earlier corrections in mind. He rewrote the ask in 2 of his last 3 edits.")).toBeVisible();
  await expect(page.getByText(/Your corrections were not applied to this run/)).toBeVisible();
});

// ---------- Second pass: dropdown groups, people map, notes, CC ----------

test("groups are dropdowns: only the open company's group starts open", async ({ page }) => {
  await open(page);
  await expect(item(page, "Tallybook")).toBeVisible();
  await expect(item(page, "Kestrel Metrics")).toBeHidden();
  await page.locator('details[data-group="Drafts to review"] > summary').click();
  await expect(item(page, "Kestrel Metrics")).toBeVisible();
});

const chart = (page: Page, domain = "kestrelmetrics.io") => page.locator(`#reach .oc[data-domain="${domain}"]`);

test("a person on a company's org chart opens their notes on the people map below", async ({ page }) => {
  await open(page);
  await chart(page).locator("[data-person]").filter({ hasText: "Ines Albrecht" }).click();
  const map = detail(page).locator(".orgmap");
  await expect(map).toHaveAttribute("open", "");
  await expect(map.locator(".org-node.to")).toContainText("Ines Albrecht");
  await expect(map.locator(".org-node.to details.person")).toHaveAttribute("open", "");
  await expect(map.locator(".org-node").filter({ hasText: "Omar Reyes" }).getByLabel("CC")).toBeVisible();
});

test("a note on a person is saved, and a ticked CC goes with the send", async ({ page }) => {
  await open(page);
  await stubAction(page, (action) => ({ status: 200, body: { record: action === "note"
    ? { ...READY, notes: { "omar@kestrelmetrics.io": "Met at SaaStr" } }
    : { ...READY, status: "Sent to me", review: { status: "Sent to me", sent_at: "2026-11-12T08:00:00+00:00", cc: ["omar@kestrelmetrics.io"], cc_delivered: [] } } } }));
  await chart(page).locator("[data-person]").filter({ hasText: "Omar Reyes" }).click();
  const omar = detail(page).locator(".org-node").filter({ hasText: "Omar Reyes" });
  await expect(omar.getByLabel("Your notes")).toBeFocused();
  await omar.getByLabel("Your notes").fill("Met at SaaStr");
  await omar.getByLabel("Your notes").blur();
  await expect(omar.getByRole("status")).toHaveText("Saved.");
  expect(bodies[0]).toMatchObject({ action: "note", person: "omar@kestrelmetrics.io", note: "Met at SaaStr" });
  await omar.getByLabel("CC").check();
  await detail(page).getByRole("button", { name: "Send to my inbox" }).click();
  expect(bodies[1]).toMatchObject({ action: "send", cc: ["omar@kestrelmetrics.io"] });
  await expect(detail(page).locator("#act-note")).toContainText("CC marked: 1; none of them were emailed.");
  await expect(chart(page).locator(".node.cc")).toContainText("Omar Reyes"); // the chart marks the CC too
});

test("one org chart per company: people branch out by team, with To, roles and the missing security seat", async ({ page }) => {
  const dub = { ...READY, domain: "dub.co", name: "Dub", others_searched: true,
    contact: { ...READY.contact, name: "Steven Tey", position: "CEO", email: "steven@dub.co", role_tier: 4 },
    others: [{ name: "Kiran", position: "Software Engineer", email: "kiran@dub.co", role_tier: null, department: "it" },
      { name: "support@dub.co", position: "", email: "support@dub.co", role_tier: null, department: "support", shared: true }] };
  await open(page, run([READY, dub, DROPPED]));
  await expect(page.locator("#reach .oc")).toHaveCount(2); // a map for each company with people; the dropped one is not mapped
  await expect(page.locator("#reach")).toContainText("1 company has no map");
  const kestrel = chart(page);
  await expect(kestrel.locator(".oc-head")).toHaveAttribute("aria-expanded", "true");
  await expect(kestrel.locator(".node.team")).toHaveText(["Security & compliance1", "Engineering1"]);
  await expect(kestrel.locator(".node.to")).toContainText("To · tier 1");
  await expect(kestrel.locator("[data-person]").filter({ hasText: "Omar Reyes" })).toContainText("Influencer");
  const d = chart(page, "dub.co");
  await expect(d.locator(".oc-tree")).toHaveCount(0); // closed until clicked
  await d.locator(".oc-head").click();
  await expect(d.locator(".oc-head")).toHaveAttribute("aria-expanded", "true");
  await expect(d.locator(".oc-head")).toBeFocused();
  await expect(d.locator(".node.team")).toHaveText(["Leadership1", "Security & compliance0", "Engineering1", "Shared inboxes1"]);
  await expect(d.locator(".node.gap")).toContainText("Hunter lists nobody in security, compliance or risk");
  await expect(d.locator(".node.to")).toContainText("Steven Tey");
  await expect(d.locator(".node.shared")).toContainText("support@");
  await expect(d.getByRole("button", { name: "Find everyone here" })).toHaveCount(0); // already searched wide
  await d.getByRole("button", { name: "Open the draft" }).click();
  await expect(page.locator('.item[aria-pressed="true"]')).toContainText("Dub");
  await expect(detail(page).locator(".org-node.to")).toContainText("Steven Tey");
});

test("Find everyone here fills a senior-only company's chart, once, and says what it costs", async ({ page }) => {
  await open(page, run([{ ...READY, others: [] }, DROPPED]));
  const more = [1, 2, 3, 4].map((i) => ({ name: `Person ${i}`, position: "Engineer", email: `p${i}@kestrelmetrics.io`, role_tier: null, department: "it" }));
  const calls = await stubAction(page, () => ({ status: 200, body: { record: { ...READY, others: more, others_searched: true } } }), 300);
  await expect(chart(page).getByText("Uses 1 Hunter search.")).toBeVisible();
  await expect(chart(page).locator("[data-person]")).toHaveCount(1);
  await chart(page).getByRole("button", { name: "Find everyone here" }).dblclick();
  await expect(chart(page).locator("[data-person]")).toHaveCount(5);
  await expect(chart(page).getByRole("button", { name: "Find everyone here" })).toHaveCount(0);
  expect(calls).toEqual(["people"]);
});

test("Find companies now asks Hunter Discover, then shows the companies it found", async ({ page }) => {
  const found = run([{ domain: "pricefx.com", status: "Researching", pending: true }], { source: "found", finished_at: null });
  const doneRun = run([DROPPED], { source: "found" });
  await open(page, [{ run: null }, found, doneRun]);
  let asked = 0;
  await page.route("**/api/discover", (r) => { asked++; return r.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ run_id: "20261112-130000", domains: ["pricefx.com"] }) }); });
  await page.route("**/api/step", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(doneRun) }));
  await page.locator(".title-row").getByRole("button", { name: "Find companies now" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("1 company found for you");
  await expect(page.locator("#flow .stage .label").first()).toHaveText("Found");
  expect(asked).toBe(1);
});

test("in a found run, companies without a draft are skipped automatically, not put in Needs you", async ({ page }) => {
  await open(page, run([BLOCKED, READY, DROPPED], { source: "found", target: 2, queue: ["next.io"] }));
  await expect(page.locator('details[data-group="Needs you"]')).toHaveCount(0);
  await expect(page.locator("#c-need")).toHaveText("0");
  await expect(page.locator('details[data-group="Skipped automatically"] summary')).toContainText("1");
  await expect(page.locator("#run-meta")).toContainText("Aiming for 2 drafts");
  await expect(item(page, "Kestrel Metrics")).toHaveAttribute("aria-pressed", "true"); // opens on the draft, not a skipped company
});

test("Find companies now explains a refusal in words", async ({ page }) => {
  await open(page, { run: null });
  await page.route("**/api/discover", (r) => r.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "Hunter has no searches left this month, so no companies were looked for." }) }));
  await page.locator(".title-row").getByRole("button", { name: "Find companies now" }).click();
  await expect(page.locator("#find-error")).toHaveText("Hunter has no searches left this month, so no companies were looked for.");
  await expect(page.locator(".title-row").getByRole("button", { name: "Find companies now" })).toBeEnabled();
});

test("a sent draft can be edited and sent again as a new version", async ({ page }) => {
  const sent = { ...READY, status: "Sent to me", review: { status: "Sent to me", sent_at: "2026-11-12T08:00:00+00:00", disagreement: 0 } };
  await open(page, run([sent, DROPPED]));
  const calls = await stubAction(page, () => ({ status: 200, body: { record: { ...READY, status: "Rewritten",
    review: { status: "Rewritten", rewritten: true, sent_at: "2026-11-12T09:00:00+00:00", versions_sent: 2, changed_parts: ["ask"],
      edited: { subject: READY.draft.subject, body: "Hi Ines,\n\nShorter.\n" } } } } }));
  await pick(page, "Kestrel Metrics");
  const d = detail(page);
  await expect(d.getByLabel("Email")).toHaveAttribute("readonly", "");
  await d.getByRole("button", { name: "Edit and send again" }).click();
  await expect(d.getByLabel("Email")).not.toHaveAttribute("readonly", "");
  await expect(d.getByLabel("Email")).toBeFocused();
  await d.getByLabel("Email").fill("Hi Ines,\n\nShorter.");
  await d.getByRole("button", { name: "Send the new version" }).click();
  expect(calls).toEqual(["send"]);
  expect(bodies[0]).toMatchObject({ action: "send", body: "Hi Ines,\n\nShorter." });
  await expect(d.getByRole("button", { name: "Edit and send again" })).toBeVisible();
  await expect(d.getByLabel("Email")).toHaveValue("Hi Ines,\n\nShorter.\n");
});

test("the flow shows each stage with who stopped where, and no feedback loop box", async ({ page }) => {
  await open(page);
  const flow = page.locator("#flow");
  await expect(flow.locator(".stage .label").filter({ hasNotText: "Stopped" })).toHaveText(["Pasted", "Pages read", "Qualified", "Person found", "Draft ready", "You reviewed"]);
  await expect(flow.locator(".stage .count")).toHaveText(["4", "3", "1", "1", "1", "0"]);
  await expect(flow.locator(".loop")).toHaveCount(0); // removed at the operator's request; the figure stays in Average disagreement
  await flow.locator(".stop").filter({ hasText: "Fernpay" }).click();
  await expect(item(page, "Fernpay")).toHaveAttribute("aria-pressed", "true"); // opened below (on a phone the card names it, not a heading)
});
