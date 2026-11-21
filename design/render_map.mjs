// Renders components-map.html to components-map.png in installed Chrome with a clean temporary profile.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
const here = fileURLToPath(new URL(".", import.meta.url));
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 2360, height: 1150 }, deviceScaleFactor: 1 });
await page.goto("file://" + here + "components-map.html");
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: here + "components-map.png" });
await browser.close();
