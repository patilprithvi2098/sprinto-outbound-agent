import { test, expect, type Page } from "@playwright/test";
import { guardDialogs, countWrites, hasHorizontalOverflow, tabUntil } from "./helpers";

// Starting a run spends Hunter searches and Claude credits, so /api/run is always stubbed here.
const SETUP = {
  claude: { ok: true, detail: "Key accepted." },
  hunter: { ok: true, detail: "Key accepted.", searches_left: 43, searches_total: 50 },
  gmail: { ok: true, detail: "Login accepted." }, storage: { ok: true, detail: "Connected." },
};
const EMPTY_RUN = { run: null };

async function open(page: Page) {
  guardDialogs(page);
  await page.route("**/api/setup-check", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(SETUP) }));
  await page.route("**/api/runs/latest", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(EMPTY_RUN) }));
  await page.route("**/api/feedback", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, drafts_counted: 0, avg_disagreement: null }) }));
  await page.route("**/api/quota", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(SETUP.hunter) }));
  await page.goto("/");
}

const check = async (page: Page, text: string) => {
  await page.getByLabel("Company domains").fill(text);
  await page.getByRole("button", { name: "Check the list" }).click();
};
const runBtn = (page: Page) => page.getByRole("button", { name: /^Run \d+ domains?$/ });

test("nothing runs until Run is pressed, and Run shows what it will spend", async ({ page }) => {
  await open(page);
  const runs = countWrites(page, "/api/run");
  await check(page, "kestrelmetrics.io\ntallybook.co\nmeera@orbitly.app");
  await expect(page.getByRole("heading", { name: "2 of 3 accepted" })).toBeVisible();
  await expect(runBtn(page)).toHaveText("Run 2 domains");
  await expect(page.getByText(/Up to 2 Hunter searches/)).toBeVisible();
  await expect(page.getByText("$0.10")).toBeVisible();
  expect(runs.count).toBe(0);
});

test("a list with no valid domains offers no Run button", async ({ page }) => {
  await open(page);
  await check(page, "meera@orbitly.app, localhost");
  await expect(page.getByRole("heading", { name: "0 of 2 accepted" })).toBeVisible();
  await expect(runBtn(page)).toHaveCount(0);
});

test("Run sends exactly one request even on a double click, then opens Review", async ({ page }) => {
  await open(page);
  let posts = 0, body: { text?: string } = {};
  await page.route("**/api/run", async (route) => {
    posts += 1;
    body = route.request().postDataJSON();
    await new Promise((r) => setTimeout(r, 600));
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ run_id: "20261112-140000", domains: ["kestrelmetrics.io"], rejected: [] }) });
  });
  await check(page, "https://www.kestrelmetrics.io/pricing");
  await runBtn(page).click();
  await expect(page.getByRole("button", { name: "Starting" })).toBeDisabled();
  await page.getByRole("button", { name: "Starting" }).click({ force: true });
  await expect(page).toHaveURL(/review\.html$/);
  expect(posts).toBe(1);
  expect(body.text).toBe("kestrelmetrics.io"); // only the cleaned, accepted domains are sent
});

test("a run already in progress is explained, and Run can be tried again", async ({ page }) => {
  await open(page);
  await page.route("**/api/run", (r) => r.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "A run is already going. Wait for it to finish." }) }));
  await check(page, "tallybook.co");
  await runBtn(page).click();
  await expect(page.getByRole("alert")).toHaveText("A run is already going. Wait for it to finish.");
  await expect(runBtn(page)).toBeEnabled();
});

test("server down while starting shows a plain message", async ({ page }) => {
  await open(page);
  await page.route("**/api/run", (r) => r.abort());
  await check(page, "tallybook.co");
  await runBtn(page).click();
  await expect(page.getByRole("alert")).toHaveText("The app is not responding. Check that the server is still running.");
});

test("keyboard only: check the list, then Run", async ({ page }) => {
  await open(page);
  let posts = 0;
  await page.route("**/api/run", async (r) => { posts += 1; await r.fulfill({ status: 202, contentType: "application/json", body: "{}" }); });
  expect(await tabUntil(page, "#domains")).toBe(true);
  await page.keyboard.type("tallybook.co");
  expect(await tabUntil(page, "#run-btn")).toBe(true);
  await page.keyboard.press("Enter");
  expect(await tabUntil(page, "#start-btn")).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/review\.html$/);
  expect(posts).toBe(1);
});

test("layout: the Run button is in view and nothing scrolls sideways", async ({ page }) => {
  await open(page);
  await check(page, Array.from({ length: 15 }, (_, i) => `northwind-analytics-${i}.io`).join("\n"));
  await expect(runBtn(page)).toBeInViewport();
  expect(await hasHorizontalOverflow(page)).toBe(false);
});

// ---------- Phase 5: quota warnings and the measured cost ----------

async function openWith(page: Page, hunterLeft: number, costPerCompany: number | null) {
  guardDialogs(page);
  const setup = { ...SETUP, hunter: { ...SETUP.hunter, searches_left: hunterLeft }, estimate: { cost_per_company: costPerCompany } };
  await page.route("**/api/setup-check", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(setup) }));
  await page.goto("/");
  await expect(page.locator("#quota")).toHaveText(`${hunterLeft} of 50`);
}

test("the cost estimate uses what earlier runs actually cost", async ({ page }) => {
  await openWith(page, 43, 0.08);
  await check(page, "kestrelmetrics.io\ntallybook.co");
  await expect(page.getByText("$0.16")).toBeVisible();
  await expect(page.locator("#quota-low")).toBeHidden();
});

test("a low Hunter quota is called out before the run, not after", async ({ page }) => {
  await openWith(page, 2, null);
  await expect(page.getByText("Running low: 2 left.")).toBeVisible();
  await check(page, "kestrelmetrics.io\ntallybook.co\nfernpay.com");
  await expect(page.getByText(/Only 2 Hunter searches are left this month/)).toBeVisible();
  await expect(runBtn(page)).toBeEnabled(); // he can still run: research and qualification need no Hunter search
});

test("no Hunter searches left is stated plainly", async ({ page }) => {
  await openWith(page, 0, null);
  await expect(page.getByText(/No searches left: runs will qualify companies but find no contacts/)).toBeVisible();
});
