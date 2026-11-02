'use strict';

const fs = require('fs');
const flag = () => process.env.FLAG
  || (fs.existsSync('/flag.txt') ? fs.readFileSync('/flag.txt', 'utf8').trim() : 'flag{local_test}');
const BOT_UUID = process.env.BOT_UUID || 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

let browser;
let chain = Promise.resolve();

async function ensureBrowser() {
  if (!browser) {
    browser = await require('puppeteer').launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
  }
  return browser;
}

async function plant(origin) {
  const page = await (await ensureBrowser()).newPage();
  try {
    await page.goto(`${origin}/${BOT_UUID}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.evaluate(async (uuid, flag) => {
      const list = await fetch(`/api/comments?page=matthew.7&scope=${uuid}`).then((r) => r.json());
      if (!list.some((c) => c.author === 'admin' && c.text === flag)) {
        await fetch('/api/comments', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ page: 'matthew.7', author: 'admin', text: flag, anchor: 7, scope: uuid }),
        });
      }
    }, BOT_UUID, flag());
  } finally {
    await page.close();
  }
}

async function doVisit(url) {
  await plant(new URL(url).origin);
  const page = await (await ensureBrowser()).newPage();
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await new Promise((r) => setTimeout(r, 5000));
  } finally {
    await page.close();
  }
}

module.exports.visit = (url) =>
  new Promise((ok, err) => (chain = chain.then(() => doVisit(url)).then(ok, err)));
