# Bugs and traps found by testing

Most of these produced **no error**: the run "succeeded" and the data was wrong. That's why this project checks counts and compares implementations, not just exit codes.

## n8n

1. **Pagination stopped one page early.** The stop condition `{{ $pageCount + 1 >= totalPages }}` returned 2 of 3 posts, with status "success". When the condition runs, `$pageCount` already counts the page just fetched. Fix: `{{ $pageCount >= Number($response.headers['x-wp-totalpages']) }}`.
2. **No `URL` class in the Code node sandbox.** `new URL(...)` works in Node.js but fails in n8n with "URL is not defined". Hostnames are parsed with a regex.
3. **`$env` is blocked in expressions in n8n 2.x** ("access to env vars denied"). Settings live in a Config (Set) node.
4. **Header names are lowercase.** WordPress sends `X-WP-TotalPages`; in `$response.headers` it is `x-wp-totalpages`.
5. **Node 22 is not enough.** n8n 2.42.5 needs Node 24. Python Code nodes also need the task runner, which a plain install lacks, so the Code nodes are JavaScript.
6. **An empty AI answer counted as "brand not cited"** in the first version of the alert workflow, which under-reported the client. Empty answers are now reported separately.

## The same rules in three languages

7. **The n8n JavaScript disagreed with Python on 4 of 5 shared test cases.** Once Python, PHP and the n8n Code node all ran on one test file (`tests/fixtures/signals_cases.json`), the JavaScript version turned out to:
   - treat `notlumi-clinic.example` as the site's own domain (`endsWith(own)` without the dot);
   - miss full-width digits like `３０％`, because JavaScript's `\d` only matches ASCII;
   - miss "Q & A" headings written with spaces;
   - round 12.5% up to 13% where Python's `format()` gives 12%.

   All four are fixed, and `n8n/test_code_nodes.js` keeps them fixed.
8. **WordPress's `modified` field is local time.** On a site set to Asia/Taipei it is 8 hours ahead of UTC, so "days since update" could be off by one. Python, PHP and n8n now all use `modified_gmt`. The live test runs the site in Asia/Taipei to catch this.
9. **Real WordPress changes the HTML before anyone measures it.** A post created without the `unfiltered_html` capability loses its `<script>` tags on save, but the text inside them stays. So one test case counted 1 statistic as raw HTML and 3 in real WordPress. The live test therefore compares Python and PHP on what WordPress actually renders, not on the fixture.

## Python and SQL

10. **Links swallowed full-width punctuation.** In `（https://b.example/y）` the `）` was captured as part of the URL. A unit test caught it, and URLs now stop at full-width punctuation.
11. **Years were counted as statistics.** "2025 年" matched the statistics pattern. 4-digit years before 年 are now excluded.
12. **Question grouping was too strict.** Character trigrams merged none of the rewordings (會痛嗎 / 會很痛嗎 scored 0.38). Bigrams with punctuation removed score them 0.62.
13. **SQLite's `printf('%.0f')` truncates.** It turned 4/15 = 26.7% into "26%", while the Python report said 27%. The SQL queries use `ROUND()` instead.
14. **A test mock requested page 100.** A regex for `page=` matched inside `per_page=100`. It now matches `[?&]page=`.

## Real API runs (Gemini)

15. **"Model overloaded" spikes outlast short retries.** In the first real run, Gemini returned HTTP 503 ("experiencing high demand") for minutes at a time, so 4 retries over about 30 seconds were not enough. The client now retries 6 times with waits of up to 60 seconds. Failures are still stored, and a re-run only re-asks those.
16. **Free tiers are smaller than they look.** Gemini's free quota ran out after 5 answers, and the run stopped cleanly on the daily-quota error. OpenCode Zen's free model returned `403 FreeTierError: can only be used from within OpenCode` for API calls. The "3 errors in a row" rule stopped that run after 3 requests instead of logging 55 failures. Each model is stored as its own engine, so these partial runs never mix with the main data.
17. **Bold text in real answers is mostly emphasis, not names.** On the real answers, "other names mentioned" was full of phrases like 購物需求 and 快速到貨, which were bolded mid-sentence. Only bold text that starts a line, list item, heading or table cell is now a candidate. That surfaced 旋轉拍賣 and Amazon, with one feature phrase (比價工具) left, which is why the list is labelled for review.
18. **Brand aliases are a recall problem.** Searching the raw GPT answers for "Yahoo" showed it writing "Yahoo購物", which none of the aliases matched. Adding it changed GPT's Yahoo count from 15/30 to 16/30. Alias lists should be checked against real answers, not written from memory.
19. **Testing 39 differences at p < 0.05 finds about 2 by chance.** The engine comparison compares 13 brands across 3 engine pairs. It now uses a Bonferroni threshold (p < 0.0013). Of 8 raw "significant" results, 6 survive; the 2 that don't (蝦皮 at p = 0.005 and p = 0.04) are shown as "could be noise".

Each fix has a test, or was re-run in n8n or WordPress, before being committed.
