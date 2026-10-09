// Runs Code.gs in Node with fake SpreadsheetApp / UrlFetchApp / Utilities to test its logic.
const fs = require('fs'); const vm = require('vm');
const pages = {
  1: [{ id: 1, link: 'https://blog.tw/a', modified: '2026-10-01T00:00:00', title: { rendered: 'GEO 指南' },
        content: { rendered: '<p>點擊率從 15% 降到 8%，2025 年研究。</p><a href="https://arxiv.org/x">paper</a><a href="https://www.blog.tw/b">internal</a>' } },
      { id: 2, link: 'https://blog.tw/b', modified: '2026-01-01T00:00:00', title: { rendered: 'SEO &amp; 內容' },
        content: { rendered: '<p>沒有來源。</p>' } }],
  2: [{ id: 3, link: 'https://blog.tw/c', modified: '2026-09-01T00:00:00', title: { rendered: 'AEO' },
        content: { rendered: '<p>超過 3 萬人</p><a href="https://news.tw/1">n</a><a href="https://news.tw/2">n</a>' } }],
};
const calls = [];
const written = {};
const ctx = {
  UrlFetchApp: { fetch: (url) => { calls.push(url); const p = Number(url.match(/[?&]page=(\d+)/)[1]);
    return { getResponseCode: () => 200, getAllHeaders: () => ({ 'x-wp-totalpages': '2' }), getContentText: () => JSON.stringify(pages[p]) }; } },
  Utilities: { sleep: () => {} },
  SpreadsheetApp: { getActiveSpreadsheet: () => ({
    getSheetByName: n => n === 'Settings' ? { getRange: () => ({ getValue: () => 'https://blog.tw/' }) } : null,
    insertSheet: n => ({ clearContents: () => {}, getRange: (r, c, nr, nc) => ({ setValues: v => { written[n] = v; } }) }) }) },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8') + '\n;result = auditBlog();', ctx);
console.log('requests:', calls.length, calls.map(u => u.match(/[?&]page=\d+/)[0]).join(','));
console.log(JSON.stringify(written.Audit));
