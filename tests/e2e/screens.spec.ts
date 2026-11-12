import { test } from "@playwright/test";
import { READY, FLAGGED, DROPPED, run } from "./fixtures";

// Captures full-page screenshots for a visual design review. Run on demand:
//   npx playwright test tests/e2e/screens.spec.ts --project=chrome
// Output: test-results/screens/<page>-<width>.png
// ADAPT: the page list.
const PAGES = [{ path: "/", name: "run", data: null }, { path: "/review.html", name: "review-empty", data: { run: null } },
  { path: "/review.html", name: "review", data: run([FLAGGED, READY, DROPPED]) }];
const WIDTHS = [375, 768, 1440];

for (const p of PAGES) {
  for (const w of WIDTHS) {
    test(`screenshot: ${p.name} at ${w}px`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: 900 });
      const setup = { claude: { ok: true, detail: "Key accepted." }, hunter: { ok: true, detail: "Key accepted.", searches_left: 43, searches_total: 50 }, gmail: { ok: true, detail: "Login accepted." } };
      await page.route("**/api/setup-check", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(setup) }));
      await page.route("**/api/quota", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(setup.hunter) }));
    await page.route("**/api/feedback", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, stored: 3, drafts_counted: 4, avg_disagreement: 0.25 }) }));
      await page.route("**/api/runs/latest", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(p.data ?? { run: null }) }));
      await page.goto(p.path);
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: `test-results/screens/${p.name}-${w}.png`, fullPage: true });
    });
  }
}
