import { chromium } from "playwright";
const out = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await p.goto("http://localhost:3100", { waitUntil: "networkidle" });
// Прокрутить страницу целиком, чтобы сработали появления по скроллу.
await p.evaluate(async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 400) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 60));
  }
  window.scrollTo(0, 0);
});
await p.waitForTimeout(3000);
const h = await p.evaluate(() => document.body.scrollHeight);
console.log("высота страницы:", h);
const overflow = await p.evaluate(() =>
  [...document.querySelectorAll("*")]
    .filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1)
    .map((e) => e.tagName + "." + (e.className?.toString().slice(0, 60) || ""))
    .slice(0, 10),
);
console.log("вылезает за экран:", overflow.length ? overflow : "ничего");
for (let i = 0; i * 844 < h && i < 12; i++) {
  await p.evaluate((y) => window.scrollTo(0, y), i * 844);
  await p.waitForTimeout(350);
  await p.screenshot({ path: `${out}/m-${String(i).padStart(2, "0")}.png` });
}
await b.close();
