/* Regenerate the static cover at the board's fixed viewport using Playwright.
 * Requires playwright and its Chromium, or CHROMIUM_EXECUTABLE for local Edge.
 * Run build_ui.py first and again after this script to embed the new JPEG.
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1024, height: 600 }, deviceScaleFactor: 1 });
    let html = fs.readFileSync(path.join(root, 'runtime/web/index.html'), 'utf8');
    // Render the original CSS ornament, never recursively capture the old cache.
    html = html.replace(/\/\* Frozen cover ornament:[\s\S]*?<\/style><\/body><\/html>$/, '</style></body></html>');
    await page.setContent(html, { waitUntil: 'load' });
    await page.addStyleTag({ content: '.shadow-hero,.shadow-menu-reveal,.shadow-home-trigger,.shadow-board-bar{visibility:hidden!important}' });
    await page.locator('.shadow-app').screenshot({
      path: path.join(root, 'source/assets/board-cover.jpg'), type: 'jpeg', quality: 94,
    });
    console.log('Static cover regenerated; rebuild index.html to embed it.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
