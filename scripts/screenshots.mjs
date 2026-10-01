// README screenshots from a running TikLocal that serves demo-media/ without login:
//   FLASK_AUTH_ENABLED=false tiklocal demo-media --port 8793
//   node scripts/screenshots.mjs
import { chromium } from 'playwright-core';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const base = process.env.BASE_URL || 'http://127.0.0.1:8793';
const out = fileURLToPath(new URL('../docs/screenshots/', import.meta.url));
const phone = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true };
const desktop = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 };

const shots = [
  { name: 'flow-mobile', device: phone, path: '/flow', flowItem: 'delaneys-falls.mp4' },
  { name: 'home-mobile', device: phone, path: '/' },
  { name: 'home-desktop', device: desktop, path: '/' },
  { name: 'library-mobile', device: phone, path: '/library?view=explore' },
  { name: 'library-desktop', device: desktop, path: '/library?view=explore' },
];

// Flow order is random, so page down until the wanted item is on screen.
async function showFlowItem(page, name) {
  for (let i = 0; i < 80; i++) {
    const current = await page.evaluate(() => {
      const el = [...document.querySelectorAll('#feed-container > *')].find((e) => e.style.display === 'block');
      return el?.dataset.name || '';
    });
    if (current.endsWith(name)) return;
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(700);
  }
  throw new Error(`Flow never showed ${name}`);
}

const browser = await chromium.launch({ channel: 'chrome' });
for (const shot of shots) {
  const context = await browser.newContext({ ...shot.device, colorScheme: 'light', reducedMotion: 'reduce' });
  const page = await context.newPage();
  await page.goto(base + shot.path, { waitUntil: 'load' });
  if (shot.flowItem) await showFlowItem(page, shot.flowItem);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}${shot.name}.jpg`, type: 'jpeg', quality: 82 });
  await context.close();
  console.log(shot.name);
}
// Hero: the desktop library with the phone Flow in front of it.
const img = (name) => `data:image/jpeg;base64,${readFileSync(`${out}${name}.jpg`).toString('base64')}`;
const hero = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.5 });
await hero.setContent(`<body style="margin:0;height:900px;background:linear-gradient(135deg,#f3eee6,#e4ddd2);position:relative;overflow:hidden">
  <img src="${img('library-desktop')}" style="position:absolute;left:70px;top:80px;width:1180px;border-radius:14px;box-shadow:0 30px 80px rgba(40,30,20,.25)">
  <img src="${img('flow-mobile')}" style="position:absolute;right:90px;top:60px;width:350px;border-radius:44px;border:10px solid #1d1b19;box-shadow:0 30px 80px rgba(40,30,20,.35)">
</body>`);
await hero.screenshot({ path: `${out}hero.jpg`, type: 'jpeg', quality: 85 });
console.log('hero');
await browser.close();
