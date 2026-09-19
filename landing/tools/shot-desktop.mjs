import { chromium } from "playwright";
const out = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.goto("http://localhost:3100", { waitUntil: "networkidle" });
await p.waitForTimeout(1200);
await p.screenshot({ path: `${out}/d-00.png` });
await p.evaluate(() => document.querySelector("#sborka").scrollIntoView());
await p.waitForTimeout(3500);
await p.screenshot({ path: `${out}/d-01.png` });
const over = await p.evaluate(() =>
  [...document.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1).length);
console.log("вылезает:", over);
await b.close();
