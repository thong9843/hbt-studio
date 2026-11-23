import fs from 'node:fs';
import readline from 'node:readline';
import { chromium } from 'playwright';

const templatePath = process.argv[2];
if (!templatePath || !fs.existsSync(templatePath)) {
  console.error('Missing template HTML path');
  process.exit(1);
}

const htmlUrl = new URL(`file:///${templatePath.replace(/\\/g, '/')}`).href;

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
});

const context = await browser.newContext({
  viewport: { width: 1080, height: 1920 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
await page.goto(htmlUrl, { waitUntil: 'load' });

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    const req = JSON.parse(line);
    if (req.cmd === 'quit') break;
    if (req.cmd === 'render') {
      await page.evaluate((state) => window.renderChatState(state), req.state);
      await page.screenshot({
        path: req.out,
        omitBackground: true,
        type: 'png',
      });
      process.stdout.write(JSON.stringify({ ok: true, out: req.out }) + '\n');
    }
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(err) }) + '\n');
  }
}

await browser.close();
