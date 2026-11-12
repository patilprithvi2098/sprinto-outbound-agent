import { test, expect, type Page } from "@playwright/test";
import { guardDialogs, hasHorizontalOverflow, tabUntil } from "./helpers";
import { READY, FLAGGED, BLOCKED, DROPPED, run } from "./fixtures";

// Every API is stubbed: /api/action would send real email, /api/quota calls Hunter.
async function open(page: Page, payload: object | object[] = run([FLAGGED, BLOCKED, READY, DROPPED])) {
  guardDialogs(page);
  const responses = Array.isArray(payload) ? payload : [payload];
  let n = 0;
  await page.route("**/api/runs/latest", (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(responses[Math.min(n++, responses.length - 1)]) }));
  await page.route("**/api/quota", (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, searches_left: 43, searches_total: 50 }) }));
  await page.goto("/review.html");
}

function stubAction(page: Page, reply: (action: string) => { status: number; body: object }, delayMs = 0) {
  const calls: string[] = [];
  return page.route("**/api/action", async (route) => {
    const { action } = route.request().postDataJSON();
    calls.push(action);
    if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
    const { status, body } = reply(action);
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  }).then(() => calls);
}

const item = (page: Page, name: string) => page.locator(".item").filter({ hasText: name });
const detail = (page: Page) => page.locator("#detail");

test("empty state when there is no run yet", async ({ page }) => {
  await open(page, { run: null });
  await expect(page.getByRole("heading", { name: "No run yet" })).toBeVisible();
  await page.getByRole("link", { name: "Go to Run" }).click();
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
  for (const s of ["Flagged", "Qualified", "Disqualified"]) await expect(page.locator(".list .chip", { hasText: s }).first()).toBeVisible();
});

test("a flagged company shows No draft, its reason as text, and Open for manual review", async ({ page }) => {
  await open(page);
  await expect(item(page, "Tallybook")).toHaveAttribute("aria-pressed", "true"); // first in Needs you is opened
  await expect(detail(page).getByRole("heading", { name: "No draft" })).toBeVisible();
  await expect(detail(page).getByText("<img src=x onerror=alert(1)>", { exact: false })).toBeVisible(); // shown, never run
  await expect(detail(page).getByRole("link", { name: "Open for manual review" })).toHaveAttribute("href", "https://tallybook.co/");
  await item(page, "orbitly.app").click();
  await expect(detail(page).getByText("site blocked automated access (HTTP 403)")).toBeVisible();
});

test("a ready draft leads with the email and keeps the reasoning under it", async ({ page }) => {
  await open(page);
  await item(page, "Kestrel Metrics").click();
  const d = detail(page);
  await expect(d.getByText("Frankfurt region and security reviews")).toBeVisible();
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
  await item(page, "Kestrel Metrics").click();
  const send = detail(page).getByRole("button", { name: "Send to my inbox" });
  await send.click();
  await expect(send).toBeDisabled();
  await send.click({ force: true });
  await expect(item(page, "Kestrel Metrics").locator(".chip")).toHaveText("Sent to me");
  await expect(detail(page).getByText(/Sent to your inbox/)).toBeVisible();
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeDisabled();
  expect(calls).toEqual(["send"]);
});

test("a failed send says so in plain words and can be retried", async ({ page }) => {
  await open(page);
  await stubAction(page, () => ({ status: 502, body: { error: "Gmail send failed (SMTPServerDisconnected). Try again." } }));
  await item(page, "Kestrel Metrics").click();
  await detail(page).getByRole("button", { name: "Send to my inbox" }).click();
  await expect(detail(page).getByRole("alert")).toHaveText("Gmail send failed (SMTPServerDisconnected). Try again.");
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeEnabled();
});

test("I rewrote it marks the draft Rewritten; Skip disables sending", async ({ page }) => {
  await open(page);
  await stubAction(page, (a) => ({ status: 200, body: { record: a === "rewrote"
    ? { ...READY, status: "Rewritten", review: { status: "Rewritten", rewritten: true } }
    : { ...READY, review: { status: "Qualified", skipped: true } } } }));
  await item(page, "Kestrel Metrics").click();
  await detail(page).getByRole("button", { name: "I rewrote it" }).click();
  await expect(item(page, "Kestrel Metrics").locator(".chip")).toHaveText("Rewritten");
  await detail(page).getByRole("button", { name: "Skip" }).click();
  await expect(detail(page).getByText("Skipped. Nothing will be sent.")).toBeVisible();
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeDisabled();
});

test("while a run is going, companies arrive as they finish", async ({ page }) => {
  const pending = { domain: "fernpay.com", status: "Researching", pending: true };
  await open(page, [run([READY, pending], { finished_at: null }), run([READY, DROPPED])]);
  await expect(page.getByText(/Researching: 1 of 2 done/)).toBeVisible();
  await expect(item(page, "fernpay.com").locator(".chip")).toHaveText("Researching");
  await expect(item(page, "Fernpay").locator(".chip")).toHaveText("Disqualified", { timeout: 6000 });
  await expect(page.locator('li[data-domain="fernpay.com"]')).toHaveClass(/arrive/);
});

test("a run cut off by a server restart says so instead of spinning", async ({ page }) => {
  await open(page, run([READY, { domain: "fernpay.com", status: "Researching", pending: true }], { finished_at: null, interrupted: true }));
  await expect(page.getByText(/The run stopped when the server stopped/)).toBeVisible();
  await expect(page.getByText("Not researched: the run stopped before this company.")).toBeVisible();
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
  expect(await tabUntil(page, 'li[data-domain="kestrelmetrics.io"] .item')).toBe(true);
  await page.keyboard.press("Enter");
  await expect(detail(page).getByText("Frankfurt region and security reviews")).toBeVisible();
  expect(await tabUntil(page, '[data-act="send"]')).toBe(true);
});

test("layout: no sideways scroll; on a phone the selected card opens in place", async ({ page }, info) => {
  await open(page);
  await item(page, "Kestrel Metrics").click();
  expect(await hasHorizontalOverflow(page)).toBe(false);
  const inCard = await page.locator('li[data-domain="kestrelmetrics.io"] #detail').count();
  expect(inCard).toBe(info.project.name === "chrome-375" ? 1 : 0);
  await expect(detail(page).getByRole("button", { name: "Send to my inbox" })).toBeVisible();
});
