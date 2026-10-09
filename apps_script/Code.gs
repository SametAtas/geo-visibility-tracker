/**
 * Google Apps Script (Extensions > Apps Script in a Google Sheet).
 * Audits a WordPress blog's GEO signals into a sheet named "Audit".
 * Put the blog URL in cell B1 of a sheet named "Settings" (e.g. https://wordpress.org/news).
 */
const STAT_RE = /(?<![\d.])(?!(?:19|20)\d\d\s*年)\d[\d,]*(?:\.\d+)?\s*(?:%|％|萬|億|倍|元|美元|人|次|年)/g;

function onOpen() {                       // adds a menu when the sheet opens
  SpreadsheetApp.getUi().createMenu('GEO tools').addItem('Audit blog now', 'auditBlog').addToUi();
}

function header_(headers, name) {          // header names can come back in any case
  const key = Object.keys(headers).find(k => k.toLowerCase() === name.toLowerCase());
  return key ? headers[key] : null;
}

function hostOf_(u) {
  return ((String(u).match(/^https?:\/\/([^\/?#:]+)/i) || [])[1] || '').toLowerCase().replace(/^www\./, '');
}

function fetchPosts_(base) {
  const posts = [];
  let page = 1, totalPages = 1;
  while (page <= totalPages) {
    const url = base + '/wp-json/wp/v2/posts?per_page=100&page=' + page + '&_fields=id,link,modified,title,content';
    const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: { 'User-Agent': 'S-geo-audit/0.1' } });
    if (res.getResponseCode() !== 200) throw new Error('HTTP ' + res.getResponseCode() + ' on page ' + page);
    totalPages = Number(header_(res.getAllHeaders(), 'X-WP-TotalPages') || 1);
    posts.push(...JSON.parse(res.getContentText()));
    page++;
    Utilities.sleep(1000);                // polite: one request per second
  }
  return posts;
}

function auditBlog() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const base = String(ss.getSheetByName('Settings').getRange('B1').getValue()).replace(/\/$/, '');
  const own = hostOf_(base);
  const rows = fetchPosts_(base).map(p => {
    const html = (p.content && p.content.rendered) || '';
    const text = html.replace(/<[^>]+>/g, ' ');
    const hosts = new Set((html.match(/href=["']https?:\/\/[^"']+/gi) || [])
      .map(h => hostOf_(h.replace(/^href=["']/i, ''))).filter(h => h && !h.endsWith(own)));
    return [p.id, p.title.rendered.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&'), p.link, text.replace(/\s/g, '').length,
            hosts.size, (text.match(STAT_RE) || []).length, p.modified];
  });
  const sheet = ss.getSheetByName('Audit') || ss.insertSheet('Audit');
  sheet.clearContents();
  const out = [['id', 'title', 'link', 'chars', 'external_sources', 'statistics', 'modified'], ...rows];
  sheet.getRange(1, 1, out.length, out[0].length).setValues(out);   // ONE write, not one call per cell
  return rows.length;
}

function installDailyTrigger() {          // run once by hand; then auditBlog runs every day around 06:00
  ScriptApp.newTrigger('auditBlog').timeBased().everyDays(1).atHour(6).create();
}
