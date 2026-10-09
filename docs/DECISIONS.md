# Design decisions

## Measurement

**1. Ask every question several times.** AI answers are sampled, so the same question gives different answers. One check per keyword per week mostly measures luck. `repeats` is a config value, and every rate in the report shows how many answers it is based on.

**2. Wilson intervals, not "p ± 1.96·SE".** The textbook interval collapses to "0% ± 0%" for 0 out of 10 and misbehaves for small samples, which is exactly this situation. Wilson stays sensible: 0/10 gives 0% to 28%.

**3. Test a change before reporting it.** Each period is compared with the previous one by a two-proportion z-test. The demo's 27% → 54% has p = 0.14, so the report says "could be noise". Telling a client a random swing is progress is worse than reporting no change.

**4. A mention is not a citation.** An AI can recommend a brand without linking to it, or link to a page without naming the brand. For a client these are different outcomes, so they are two metrics.

**5. Empty answers and errors are not misses.** They say nothing about the brand. They are left out of the rates and shown in a data-quality table.

**6. Measure stability directly.** Besides rates, the report says how often a brand appeared in some runs of a question but not others, and how often a single check would disagree with the majority of runs. That makes the case for repeats with the client's own data.

**7. Real runs ask the question and nothing else.** No system prompt and the provider's default temperature, because that is the closest an API gets to a person typing the question. Both can be set in the config, and the report names the model. An API answer is still not the same as the ChatGPT app or Google's AI Overviews: for those, a licensed data provider can plug in behind the same `ask(keyword, run)` interface.

**8. No LLM in the measurement path.** Parsing, metrics and fact-checking are deterministic: same input, same output. Using an LLM to judge LLM answers would add its own randomness and errors to the number. An LLM could give a second opinion on `weak` fact-check cells, never the verdict.

## Data

**9. Keep raw answers and recompute everything.** Storage is cheap, and re-collecting is expensive (impossible for past weeks). Parser fixes and new metrics apply to history.

**10. Runs can be interrupted.** A unique key per (date, engine, keyword, run) with an upsert makes re-running safe. Answers already stored are skipped, so after a crash, a quota limit or a closed laptop, running the same command again continues. A daily-quota error stops the run at once, and so do three errors in a row: past that point it would only collect more errors.

**11. SQL views over the raw table, with the status decided in Python.** Analysts and dashboards get plain SQL views (rates, Wilson intervals, `LAG` for change, window sums for share of voice). Whether an answer is valid, empty or an error is written by the same Python code the reports use, so the two can't disagree about which answers count. Tests check every view against the Python numbers.

**12. `.example` domains for the sample data.** The demo looks realistic but can never be mistaken for a measurement of a real company. The real-data study names real platforms, because its answers are real.

## Content audit

**13. One set of rules, three implementations, one test file.** The audit runs in Python (CLI and API), in PHP (the WordPress plugin, so editors see it on the Posts screen) and in JavaScript (the n8n Code node). A single shared test file runs against all three, and the live WordPress test compares Python and PHP on every real post. Without that file, the JavaScript version had quietly drifted on 4 of 5 cases (FINDINGS.md #7).

**14. WordPress REST API, not HTML scraping.** It gives structured fields, survives theme changes, has pagination headers and is lighter on the site. Requests are 1 second apart by default.

**15. The plugin caches per post and is read-only.** Signals are computed on save and cached in post meta, keyed to the post's modification time and the plugin version. The REST endpoints are public because they only return numbers derived from posts that `/wp/v2/posts` already publishes.

**16. Character bigrams for Chinese similarity.** No word segmentation or model download is needed, and the behaviour is deterministic and explainable. Trigrams were too strict for short questions. Limitation: synonyms written with different characters are not merged.

## Automation

**17. n8n for orchestration, code for logic.** n8n handles schedules, HTTP calls and alerts, and non-engineers can read the flow. Logic that needs tests lives in Python or PHP and is called over HTTP. The JavaScript Code nodes are small and tested outside n8n on the shared cases.

**18. Secrets come from the environment only.** The API key is read from `GEO_LLM_API_KEY` and never written to the config, the database or the exported data. In n8n, keys belong in Credentials. rein checks the repository for committed secrets.
