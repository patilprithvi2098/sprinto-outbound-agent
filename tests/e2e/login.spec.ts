import { test, expect, type Page } from "@playwright/test";
import { guardDialogs, countWrites, hasHorizontalOverflow, tabUntil } from "./helpers";

// /api/login is always stubbed: the real one would set a session cookie when APP_PASSWORD is set.
async function open(page: Page, next = "review.html") {
  guardDialogs(page);
  await page.goto("/login.html?next=" + next);
}
const box = (page: Page) => page.getByLabel("App password");
const submit = (page: Page) => page.getByRole("button", { name: "Sign in" });

test("empty password sends nothing", async ({ page }) => {
  await open(page);
  const writes = countWrites(page, "/api/login");
  await submit(page).click();
  await expect(page.getByRole("alert")).toHaveText("Enter the app password.");
  expect(writes.count).toBe(0);
});

test("wrong password says so and keeps the operator here", async ({ page }) => {
  await open(page);
  await page.route("**/api/login", (r) => r.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: "That password is not right." }) }));
  await box(page).fill("guess");
  await submit(page).click();
  await expect(page.getByRole("alert")).toHaveText("That password is not right.");
  await expect(page).toHaveURL(/login\.html/);
});

test("right password goes back to the page that asked, once, even on a double click", async ({ page }) => {
  await open(page, "review.html");
  let posts = 0;
  await page.route("**/api/login", async (r) => { posts += 1; await new Promise((x) => setTimeout(x, 400)); await r.fulfill({ contentType: "application/json", body: "{\"ok\":true}" }); });
  await page.route("**/api/runs/latest", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ run: null }) }));
  await page.route("**/api/quota", (r) => r.fulfill({ contentType: "application/json", body: "{}" }));
  await page.route("**/api/feedback", (r) => r.fulfill({ contentType: "application/json", body: "{}" }));
  await box(page).fill("correct horse");
  await submit(page).click();
  await submit(page).click({ force: true });
  await expect(page).toHaveURL(/review\.html$/);
  expect(posts).toBe(1);
});

test("the next page can only be one of the app's own pages", async ({ page }) => {
  await open(page, encodeURIComponent("https://evil.example/"));
  await page.route("**/api/login", (r) => r.fulfill({ contentType: "application/json", body: "{\"ok\":true}" }));
  await page.route("**/api/setup-check", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ claude: { ok: true, detail: "" }, hunter: { ok: true, detail: "", searches_left: 42, searches_total: 50 }, gmail: { ok: true, detail: "" } }) }));
  await box(page).fill("correct horse");
  await submit(page).click();
  await expect(page).toHaveURL(/127\.0\.0\.1:8321\/index\.html$/);
});

test("very long input is capped and the layout holds", async ({ page }) => {
  await open(page);
  await box(page).fill("x".repeat(500));
  expect((await box(page).inputValue()).length).toBe(200);
  expect(await hasHorizontalOverflow(page)).toBe(false);
  await expect(submit(page)).toBeInViewport();
});

test("keyboard only: type and press Enter", async ({ page }) => {
  await open(page);
  let posts = 0;
  await page.route("**/api/login", async (r) => { posts += 1; await r.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: "That password is not right." }) }); });
  await expect(box(page)).toBeFocused();
  await page.keyboard.type("guess");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toHaveText("That password is not right.");
  expect(await tabUntil(page, "#login-btn")).toBe(true);
  expect(posts).toBe(1);
});
