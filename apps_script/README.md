# Google Apps Script version of the blog audit

1. In a Google Sheet, name a tab `Settings` and put a WordPress site URL in B1 (e.g. `https://wordpress.org/news`).
2. *Extensions → Apps Script*, paste `Code.gs`, save, run `auditBlog` (authorize on first run).
3. An `Audit` tab appears; reload the sheet for the **GEO tools** menu. Run `installDailyTrigger` once for a daily run.

Writes all rows with one `setValues()` call (cell-by-cell writes are the classic slow Apps Script).
Test without Google: `node test_gs.js Code.gs` (simulated SpreadsheetApp, UrlFetchApp, Utilities).
