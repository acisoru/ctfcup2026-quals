'use strict';

const fs = require('fs');
const crypto = require('crypto');
const flag = () => process.env.FLAG
  || (fs.existsSync('/flag.txt') ? fs.readFileSync('/flag.txt', 'utf8').trim() : 'flag{local_test}');
const BOT_UUID = crypto.randomUUID();
let BOT_PASS = '';
module.exports.setPass = (p) => BOT_PASS = p;
const ORIGIN = process.env.APP_URL || `http://127.0.0.1:${process.env.PORT || 3000}`;

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
  if (origin !== ORIGIN) throw new Error(`чужой origin: ${origin}`);
  const page = await (await ensureBrowser()).newPage();
  try {
    await page.goto(`${origin}/${BOT_UUID}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.evaluate(async (uuid, flag, pass) => {
      document.cookie = 'botpass=' + pass + '; path=/';
      const list = await fetch(`/api/comments?page=matthew.7&scope=${uuid}`).then((r) => r.json());
      if (!list.some((c) => c.author === 'admin' && c.text === flag)) {
        await fetch('/api/comments', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ page: 'matthew.7', author: 'admin', text: flag, anchor: 7, scope: uuid }),
        });
      }
    }, BOT_UUID, flag(), BOT_PASS);
  } finally {
    await page.close();
  }
}

async function doVisit(url) {
  const u = new URL(url);
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error(`протокол ${u.protocol} запрещён`);
  if (u.origin !== ORIGIN) throw new Error(`чужой origin: ${u.origin}`);
  await plant(u.origin);
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
