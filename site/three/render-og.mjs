// Render the social images into site/src/og/ (committed; the site build only copies them):
//   og.png                1200 x 630   Open Graph / Twitter banner, from /og-card/ (site/og/card.html), in dark mode
//   apple-touch-icon.png  180 x 180    the mark on a dark square tile (from /og-card/icon.svg; the OS rounds it)
//   icon-192.png, icon-512.png         the same, for the web app manifest
// Usage: build the site, serve site/dist on a port, then
//   cd site/three && npm install && npm run og -- http://127.0.0.1:8791 [path/to/chrome]
// Needs a Chrome (playwright-core drives it); WebGL runs on SwiftShader if there is no GPU.
import { chromium } from 'playwright-core';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const [base = 'http://127.0.0.1:8791', exe] = process.argv.slice(2);
const out = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src', 'og');
const browser = await chromium.launch({ executablePath: exe, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

const card = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1, colorScheme: 'dark' });   // the social images are dark
await card.goto(base + '/og-card/', { waitUntil: 'load' });
await card.waitForTimeout(6000);   // crystals rise, the sun moves onto an edge
await card.screenshot({ path: path.join(out, 'og.png') });

for (const [name, size] of [['apple-touch-icon.png', 180], ['icon-192.png', 192], ['icon-512.png', 512]]) {
  const p = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
  await p.setContent(`<html><body style="margin:0"><img src="${base}/og-card/icon.svg" style="width:${size}px;height:${size}px;display:block"></body></html>`);
  await p.waitForTimeout(300);
  await p.screenshot({ path: path.join(out, name), omitBackground: true });
}
await browser.close();
console.log('wrote', out);
