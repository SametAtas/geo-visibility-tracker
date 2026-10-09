# Product spec: AI visibility tracker for an SEO/GEO team

Status: MVP built (this repo). Written before and during the build; updated with what testing showed.

## 1. The real need (not the surface request)

**Surface request:** "Tell us if our clients appear in ChatGPT / AI Overviews."

**Underlying need, found by asking "what decision will this number drive?":**
- Consultants need to **show clients whether GEO work is paying off**, month by month.
- They need to **know where to act**: which keywords, which competitors win, which third-party sites the AI trusts.
- They must **not report noise as progress**. AI answers change between runs. A client told "+27%" who later sees it vanish loses trust in the agency.

So the product is not "a scraper". It is **a measurement with error bars**, plus pointers to action.

## 2. Users and scenarios

| User | Scenario | What they need |
|---|---|---|
| SEO/GEO consultant | Weekly check for each client | A report: rates with ranges, change vs last week, and whether the change is real |
| Content writer | Plans next month's articles | A question bank from real forum questions; which articles lack sources and statistics |
| Editor | Reviews an AI-generated comparison table before publishing | Which cells are unsupported or invented |
| Automation owner | Runs everything on a schedule | A CLI and an API that n8n can call; failures that alert instead of vanishing |
| Client (indirect) | Reads the monthly report | Plain numbers, honest about uncertainty |

**Edge cases that shaped the design:**
- **Empty AI answer.** That's a collection problem, not "not cited"; it's counted separately.
- **API error mid-run.** The error is stored per keyword and run; the rest of the run continues; re-running is safe (upsert).
- **Brand named but not linked** (or linked but not named): mention and citation are separate metrics.
- **Brand written in full-width characters or with an alias:** normalization handles it.
- **Look-alike domains** (`notlumi-clinic.example`) must not count; subdomains (`blog.lumi-clinic.example`) must.
- **Table cell says "not mentioned":** honest, so it's counted but not flagged.
- **Source page down:** the cell is "unreachable", never "supported".

## 3. Scope

| In (MVP) | Later | Out |
|---|---|---|
| OpenAI-compatible API adapter, replay adapter | SERP/AI Overview provider adapter (licensed data) | Scraping Google results directly (Google's robots.txt disallows /search) |
| Mention and citation rates, Wilson intervals, z-test, share of voice | Sentiment of mentions, position-weighted visibility | Automatic sending of reports to clients |
| Question mining from titles (character similarity) | Embedding-based grouping | Collecting from sites whose terms forbid it |
| Table fact-check (evidence and numbers) | LLM-assisted semantic check as a *second opinion* | Auto-"fixing" table cells |
| WordPress REST audit | JSON-LD schema audit from page `<head>` | |
| HTML report, CLI, API, n8n, Apps Script | Dashboard over history | |

**Explicitly not doing:** using an LLM to *measure* the LLM. Parsing and fact-checking are deterministic, so the same input always gives the same number.

## 4. MVP and how it was validated

**Riskiest assumption:** a weekly visibility number is stable enough to report.

**Cheapest test:** the demo data. 5 keywords × 3 runs × 2 weeks. The result was 27% → 54% mention rate, which looks like a big win, but **p = 0.14: not distinguishable from noise** with this sample.

**Decision that follows:** for client reporting, raise repeats and keywords until intervals are useful. About 97 independent checks give roughly ±10 points, and about 385 give ±5. Show intervals in every report.

## 5. Data flow

Source (LLM API / replay) → collect (rate limit, retries, errors stored) → **raw answers in SQLite** (unique key per date, engine, keyword and run) → parse (normalize, mentions, citations) → metrics (rates, intervals, tests) → report (HTML) / API (JSON) → n8n alerting. Diagram: [DATA_FLOW.md](DATA_FLOW.md).

Raw answers are kept and every metric is recomputed from them, so a parser fix or a new metric never needs re-collection.

## 6. What to automate and what a human checks

**Rule:** automate when the steps are fixed, mistakes are easy to detect, and a mistake is cheap. Keep a human when the output goes to a client or a mistake is hard to notice.

| Step | Automated | Human |
|---|---|---|
| Collecting answers, parsing, metrics | Yes | Reviews data-quality counts (empty answers, errors) |
| Deciding "visibility improved" | The significance test flags it | The consultant decides what to tell the client |
| Question bank | Grouping and intent tags | The writer picks topics; merges synonyms the tool missed |
| Table fact-check | `supported`, `no_source`, `value_not_in_source` | Every `weak`, `evidence_not_found` and `unreachable` cell |
| Sending reports | No | Always reviewed first |

## 7. Acceptance criteria (all covered by tests)

- Re-running a collection for the same day does not duplicate rows.
- Empty answers and errors never count as "not cited".
- `27% → 54%` on 13 to 15 answers is reported as "could be noise".
- A table cell whose number is not on the cited page is flagged `value_not_in_source`.
- Every untrusted string in the HTML report is escaped.
- The n8n workflows run successfully in n8n 2.42.5.

## 8. Working with non-engineers

The report is written for consultants, not engineers:
- "54% (29% to 77%)" instead of "p̂ = 0.54";
- one sentence under the chart explaining why the band is wide;
- the significance result as plain words ("could be noise").

Limits are stated in the README, so nobody over-promises to a client.
