import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { READY, FLAGGED, DROPPED, run } from "./fixtures";

// ADAPT: one entry per page/route in the app.
const PAGES = [
  { path: "/", name: "Run" },
  { path: "/review.html", name: "Review (empty)", data: { run: null } },
  { path: "/review.html", name: "Review (flagged open)", data: run([FLAGGED, READY, DROPPED]) },
  { path: "/review.html", name: "Review (draft open)", data: run([READY, DROPPED]) },
] as { path: string; name: string; data?: object }[];

for (const p of PAGES) {
  test(`accessibility: ${p.name} page has no WCAG A/AA violations`, async ({ page }) => {
    const setup = { claude: { ok: true, detail: "Key accepted." }, hunter: { ok: true, detail: "Key accepted.", searches_left: 43, searches_total: 50 }, gmail: { ok: true, detail: "Login accepted." } };
    await page.route("**/api/setup-check", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(setup) }));
    await page.route("**/api/quota", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(setup.hunter) }));
    await page.route("**/api/feedback", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, stored: 3, drafts_counted: 4, avg_disagreement: 0.25 }) }));
    await page.route("**/api/runs/latest", (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(p.data ?? { run: null }) }));
    await page.goto(p.path);
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const summary = results.violations.map((v) => ({
      rule: v.id,
      impact: v.impact,
      help: v.help,
      count: v.nodes.length,
      examples: v.nodes.slice(0, 3).map((n) => `${n.target.join(" ")} :: ${n.failureSummary?.split("\n").slice(1).join(" ").trim()}`),
    }));
    if (summary.length) console.log(`\n[${p.name}] ${JSON.stringify(summary, null, 2)}`);
    expect(summary, `${p.name} accessibility violations`).toEqual([]);
  });
}
