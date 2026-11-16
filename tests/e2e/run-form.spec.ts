import { test, expect, type Page } from "@playwright/test";
import { guardDialogs, countWrites, hasHorizontalOverflow, tabUntil } from "./helpers";

// /api/domains only validates text and writes nothing, so it is safe to hit for real.
// /api/setup-check calls Claude, Hunter and Gmail when keys exist, so it is always stubbed here.
const SETUP = {
  claude: { ok: true, detail: "Key accepted." },
  hunter: { ok: true, detail: "Key accepted.", searches_left: 19, searches_total: 50 },
  gmail: { ok: false, detail: "Not set. Add OPERATOR_EMAIL and GMAIL_APP_PASSWORD to .env." }, storage: { ok: true, detail: "Connected." },
};

async function open(page: Page) {
  guardDialogs(page);
  const calls = { count: 0 };
  await page.route("**/api/setup-check", async (route) => {
    calls.count += 1;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(SETUP) });
  });
  await page.goto("/");
  return calls;
}

const box = (page: Page) => page.getByLabel("Company domains");
const submit = (page: Page) => page.getByRole("button", { name: "Check the list" });

test("empty submit sends nothing and says what to do", async ({ page }) => {
  await open(page);
  const writes = countWrites(page, "/api/domains");
  await submit(page).click();
  await expect(page.getByRole("alert")).toHaveText("Paste at least one domain.");
  await box(page).fill("   \n  ");
  await submit(page).click();
  await expect(page.getByRole("alert")).toHaveText("Paste at least one domain.");
  expect(writes.count).toBe(0);
});

test("invalid entries are refused with a plain reason each", async ({ page }) => {
  await open(page);
  await box(page).fill("notadomain, meera@orbitly.app\nlocalhost 127.0.0.1 <script>alert(1)</script>");
  await submit(page).click();
  await expect(page.getByRole("heading", { name: "0 of 5 accepted" })).toBeVisible();
  await expect(page.getByText("This is an email address, not a domain.")).toBeVisible();
  await expect(page.getByText("Not a public domain name.")).toHaveCount(4);
  await expect(page.getByText("<script>alert(1)</script>")).toBeVisible(); // shown as text, never run
});

test("very long input is refused quickly with a human message", async ({ page }) => {
  await open(page);
  await box(page).fill("a".repeat(400) + ".com");
  await submit(page).click();
  await expect(page.getByRole("heading", { name: "0 of 1 accepted" })).toBeVisible();
  expect(await hasHorizontalOverflow(page)).toBe(false);

  await box(page).fill("company.com ".repeat(3000));
  await submit(page).click();
  await expect(page.getByRole("alert")).toHaveText("That list is too long. Paste at most 15 domains.");
});

test("valid list is cleaned, deduped and capped at 15", async ({ page }) => {
  await open(page);
  await box(page).fill("https://www.Kestrelmetrics.io/pricing\ntallybook.co, kestrelmetrics.io");
  await expect(page.getByText("3 domains", { exact: true })).toBeVisible();
  await submit(page).click();
  await expect(page.getByRole("heading", { name: "2 of 3 accepted" })).toBeVisible();
  await expect(page.getByText("Duplicate of a domain already in the list.")).toBeVisible();

  await box(page).fill(Array.from({ length: 17 }, (_, i) => `company${i}.com`).join("\n"));
  await submit(page).click();
  await expect(page.getByRole("heading", { name: "15 of 17 accepted" })).toBeVisible();
  await expect(page.getByText("Over the 15-domain cap for one run.")).toHaveCount(2);
});

test("double submit sends exactly one request", async ({ page }) => {
  await open(page);
  let posts = 0;
  await page.route("**/api/domains", async (route) => {
    posts += 1;
    await new Promise((r) => setTimeout(r, 600));
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ valid: ["tallybook.co"], rejected: [], cap: 15 }) });
  });
  await box(page).fill("tallybook.co");
  await submit(page).click();
  await expect(submit(page)).toBeDisabled();
  await submit(page).click({ force: true });
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "1 of 1 accepted" })).toBeVisible();
  expect(posts).toBe(1);
  await expect(submit(page)).toBeEnabled();
});

test("keyboard only: reach the box, type, submit, then clear", async ({ page }) => {
  await open(page);
  expect(await tabUntil(page, "#domains")).toBe(true);
  await page.keyboard.type("tallybook.co");
  expect(await tabUntil(page, "#run-btn")).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "1 of 1 accepted" })).toBeVisible();
  expect(await tabUntil(page, "#clear-btn")).toBe(true);
  await page.keyboard.press("Enter");
  await expect(box(page)).toHaveValue("");
  await expect(box(page)).toBeFocused();
  await expect(page.getByRole("heading", { name: "1 of 1 accepted" })).toHaveCount(0);
});

test("server down shows a plain message, not a stack trace", async ({ page }) => {
  await open(page);
  await page.route("**/api/domains", (route) => route.abort());
  await box(page).fill("tallybook.co");
  await submit(page).click();
  await expect(page.getByRole("alert")).toHaveText("The app is not responding. Check that the server is still running.");
  await expect(submit(page)).toBeEnabled();
});

test("setup check shows each credential with a label, and the Hunter quota", async ({ page }) => {
  const calls = await open(page);
  await expect(page.getByText("19 of 50")).toBeVisible();
  await expect(page.getByText("Working")).toHaveCount(3);
  await expect(page.getByText("Needs you")).toHaveCount(1);
  await expect(page.getByText("Not set. Add OPERATOR_EMAIL and GMAIL_APP_PASSWORD to .env.")).toBeVisible();
  await page.getByRole("button", { name: "Check again" }).click();
  await expect.poll(() => calls.count).toBe(2);
});

test("layout: no sideways scroll and the submit button is in view", async ({ page }) => {
  await open(page);
  expect(await hasHorizontalOverflow(page)).toBe(false);
  await expect(submit(page)).toBeInViewport();
});
