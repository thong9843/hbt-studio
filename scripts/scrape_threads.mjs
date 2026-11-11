#!/usr/bin/env node
/**
 * Cuộn sâu & bóc tách bình luận Threads bằng Playwright Chromium.
 * Kết hợp bắt trực tiếp GraphQL pagination (`BarcelonaPostPageDirectRepliesRefetchQuery`),
 * thẻ `<script type="application/json">` và DOM thực tế qua các nhịp cuộn.
 *
 * Usage: node scripts/scrape_threads.mjs <url> [target_comments=50]
 */

import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('@playwright/test');

const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

function extractNextCursor(jsonTexts) {
  let cursor = null;
  for (const txt of jsonTexts) {
    const matches = [
      ...txt.matchAll(/"end_cursor"\s*:\s*"([^"]+)"\s*,\s*"has_next_page"\s*:\s*true/g),
    ];
    if (matches.length > 0) {
      cursor = matches[matches.length - 1][1];
    }
  }
  return cursor;
}

function collectParentCandidates(jsonTexts, mainTextNorm) {
  const byPk = new Map();
  const walk = (n) => {
    if (!n || typeof n !== 'object') return;
    if (Array.isArray(n)) {
      for (const x of n) walk(x);
      return;
    }
    const pk = n.pk ? String(n.pk) : '';
    const text = typeof n.caption?.text === 'string' ? n.caption.text.trim() : '';
    const rc = Number(n.text_post_app_info?.direct_reply_count || 0);
    const likes = Number(n.like_count || 0);
    if (pk && n.user?.username && text && rc > 0) {
      const norm = text.normalize('NFC').toLowerCase();
      if (norm !== mainTextNorm && !byPk.has(pk)) {
        byPk.set(pk, { pk, text, norm, rc, likes, score: likes + rc * 20 });
      }
    }
    for (const v of Object.values(n)) walk(v);
  };
  for (const txt of jsonTexts) {
    if (!txt || (!txt.includes('"direct_reply_count"') && !txt.includes('"caption"'))) continue;
    try {
      walk(JSON.parse(txt));
    } catch {
      // bỏ qua JSON không parse được
    }
  }
  return Array.from(byPk.values()).sort((a, b) => b.score - a.score);
}

async function fetchChildReplies(page, templateReq, parentPk) {
  return page
    .evaluate(
      async ({ url, postData, headers, pk }) => {
        const params = new URLSearchParams(postData);
        const vars = JSON.parse(params.get('variables') || '{}');
        vars.postID = pk;
        vars.after = null;
        vars.first = 6;
        params.set('variables', JSON.stringify(vars));
        const resp = await fetch(url, {
          method: 'POST',
          headers: {
            'content-type': 'application/x-www-form-urlencoded',
            'x-fb-friendly-name':
              headers['x-fb-friendly-name'] || 'BarcelonaPostPageDirectRepliesRefetchQuery',
            'x-fb-lsd': headers['x-fb-lsd'] || '',
            'x-ig-app-id': headers['x-ig-app-id'] || '',
          },
          body: params.toString(),
          credentials: 'include',
        });
        return await resp.text();
      },
      { ...templateReq, pk: parentPk },
    )
    .catch(() => '');
}

function countCaptionCandidates(jsonTexts) {
  let total = 0;
  for (const txt of jsonTexts) {
    const m = txt.match(/"caption"\s*:/g);
    if (m) total += m.length;
  }
  return total;
}

async function dismissDialogs(page) {
  await page.keyboard.press('Escape').catch(() => {});
  await page
    .evaluate(() => {
      for (const btn of document.querySelectorAll('[role="button"], button')) {
        const label = (btn.getAttribute('aria-label') || btn.innerText || '').trim();
        if (/^(close|đóng|not now|lúc khác|x)$/i.test(label)) {
          try {
            btn.click();
          } catch {
            // bỏ qua lỗi click nút đóng modal
          }
        }
      }
    })
    .catch(() => {});
}

async function scrollContainerStep(page) {
  return page
    .evaluate(() => {
      for (const el of document.querySelectorAll('button, [role="button"], span, a')) {
        const text = (el.innerText || '').trim();
        if (
          /^(xem thêm|view more|show more|xem .* phản hồi|view .* repl|load more)/i.test(text) &&
          text.length < 60
        ) {
          try {
            el.click();
          } catch {
            // bỏ qua nếu không click được
          }
        }
      }
      const container = Array.from(document.querySelectorAll('*')).find((el) => {
        const st = getComputedStyle(el);
        return (
          (st.overflowY === 'auto' || st.overflowY === 'scroll') &&
          el.scrollHeight > el.clientHeight + 20
        );
      });
      if (container) {
        const prev = container.scrollTop;
        container.scrollTop += 1200;
        return { moved: container.scrollTop > prev, top: container.scrollTop };
      }
      const prevY = window.scrollY;
      window.scrollBy(0, 1200);
      return { moved: window.scrollY > prevY, top: window.scrollY };
    })
    .catch(() => ({ moved: false, top: 0 }));
}

async function main() {
  const targetUrl = process.argv[2];
  const targetComments = Math.max(15, Number.parseInt(process.argv[3] || '50', 10) || 50);
  if (!targetUrl) {
    console.error('Missing URL argument');
    process.exit(2);
  }

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({
      userAgent: DEFAULT_UA,
      locale: 'vi-VN',
      viewport: { width: 1280, height: 1000 },
    });
    const page = await ctx.newPage();

    const graphqlPayloads = [];
    const seenPayloads = new Set();
    let collectingMainResponses = true;
    let templateReq = null;

    page.on('request', (req) => {
      if (!collectingMainResponses) return;
      const url = req.url();
      const postData = req.postData() || '';
      if (
        url.includes('/api/graphql') &&
        postData.includes('BarcelonaPostPageDirectRepliesRefetchQuery')
      ) {
        templateReq = {
          url,
          postData,
          headers: req.headers(),
        };
      }
    });

    page.on('response', async (resp) => {
      if (!collectingMainResponses) return;
      const url = resp.url();
      if (!url.includes('/api/graphql')) return;
      try {
        const txt = await resp.text();
        if (
          txt &&
          (txt.includes('direct_replies') ||
            txt.includes('thread_items') ||
            txt.includes('"caption"')) &&
          !seenPayloads.has(txt)
        ) {
          seenPayloads.add(txt);
          graphqlPayloads.push(txt);
        }
      } catch {
        // bỏ qua response stream đã đóng
      }
    });

    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 25000 });
    await page.waitForTimeout(2200);
    await dismissDialogs(page);

    // Thu thập khối text DOM qua từng nhịp cuộn để chống mất node do virtual scrolling
    const domChunks = [];
    const seenDomChunks = new Set();
    const captureDomSnapshot = async () => {
      const raw = await page.evaluate(() => document.body?.innerText || '').catch(() => '');
      for (const lineBlock of raw.split(/\n{2,}/)) {
        const clean = lineBlock.trim();
        if (clean && !seenDomChunks.has(clean)) {
          seenDomChunks.add(clean);
          domChunks.push(clean);
        }
      }
    };

    await captureDomSnapshot();
    for (let step = 0; step < 8; step++) {
      await scrollContainerStep(page);
      await page.waitForTimeout(850);
      await captureDomSnapshot();
      if (templateReq && countCaptionCandidates(graphqlPayloads) >= targetComments) {
        break;
      }
    }

    // Phân trang trực tiếp qua GraphQL cursor để lấy sâu 30-50+ bình luận kể cả khi bị tường đăng nhập chặn cuộn UI
    let nextCursor = extractNextCursor(graphqlPayloads);
    let pageCalls = 0;
    const maxPageCalls = 12;
    const seenCursors = new Set();

    while (
      templateReq &&
      nextCursor &&
      !seenCursors.has(nextCursor) &&
      pageCalls < maxPageCalls &&
      countCaptionCandidates(graphqlPayloads) < targetComments + 15
    ) {
      seenCursors.add(nextCursor);
      pageCalls += 1;
      const respText = await page
        .evaluate(
          async ({ url, postData, headers, cursor }) => {
            const params = new URLSearchParams(postData);
            const vars = JSON.parse(params.get('variables') || '{}');
            vars.after = cursor;
            params.set('variables', JSON.stringify(vars));
            const resp = await fetch(url, {
              method: 'POST',
              headers: {
                'content-type': 'application/x-www-form-urlencoded',
                'x-fb-friendly-name':
                  headers['x-fb-friendly-name'] || 'BarcelonaPostPageDirectRepliesRefetchQuery',
                'x-fb-lsd': headers['x-fb-lsd'] || '',
                'x-ig-app-id': headers['x-ig-app-id'] || '',
              },
              body: params.toString(),
              credentials: 'include',
            });
            return await resp.text();
          },
          { ...templateReq, cursor: nextCursor },
        )
        .catch(() => '');

      if (!respText || !respText.includes('"data"')) break;
      if (!seenPayloads.has(respText)) {
        seenPayloads.add(respText);
        graphqlPayloads.push(respText);
      }
      const next = extractNextCursor([respText]);
      nextCursor = next && !seenCursors.has(next) ? next : null;
    }

    const pageData = await page.evaluate(() => {
      const og = {};
      for (const m of document.querySelectorAll('meta[property], meta[name]')) {
        const key = m.getAttribute('property') || m.getAttribute('name');
        const val = m.getAttribute('content');
        if (key && val != null && !(key in og)) {
          og[key] = val;
        }
      }
      const scripts = Array.from(document.querySelectorAll('script[type="application/json"]'))
        .map((s) => s.textContent || '')
        .filter(Boolean);
      return {
        final_url: window.location.href,
        title: document.title,
        og,
        scripts,
      };
    });

    // Bóc tách thêm mảng replies con dưới các bình luận cha nhiều tương tác
    collectingMainResponses = false;
    const childReplyBlobs = [];
    if (templateReq) {
      const mainRaw = (pageData.og['og:description'] || pageData.og.description || '')
        .replace(/\s*•\s*Threads,\s*Say more\s*$/i, '')
        .trim()
        .normalize('NFC')
        .toLowerCase();
      const candidates = collectParentCandidates(
        [...pageData.scripts, ...graphqlPayloads],
        mainRaw,
      ).slice(0, 6);
      for (const parent of candidates) {
        const childPayload = await fetchChildReplies(page, templateReq, parent.pk);
        if (childPayload && childPayload.includes('"direct_replies"')) {
          childReplyBlobs.push({
            parent_text: parent.text,
            payload: childPayload,
          });
        }
      }
    }

    process.stdout.write(
      JSON.stringify({
        ...pageData,
        graphql_payloads: graphqlPayloads,
        child_reply_blobs: childReplyBlobs,
        dom_text: domChunks.join('\n\n'),
      }),
    );
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
