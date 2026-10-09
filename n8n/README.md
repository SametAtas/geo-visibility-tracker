# n8n workflows

Every workflow here was imported and executed in n8n 2.42.5 before being committed.

**`geo_audit_workflow.json`**: Manual Trigger → Config → HTTP Request (WordPress REST API with pagination) → Code (signals per post) → Code (blog summary).
- Run against a real WordPress 7.1.3 (`tests/wordpress/setup_wordpress.sh`) at 10 posts per page, it fetched all 23 posts over 3 pages.
- Its signals matched the PHP plugin on every post, and its summary matched the plugin's `/summary` and the Python audit exactly.
- The Code node's JavaScript is also tested outside n8n on the shared cases: `node n8n/test_code_nodes.js`.

**`wordpress_plugin_check_workflow.json`**: Manual Trigger → Config → HTTP Request to the plugin's `/wp-json/geo-signals/v1/summary` → Code (what needs attention).
- It's the weekly check, with the PHP plugin doing the counting.
- Against the test site it returned 3 problems (sources, statistics, FAQ).

**`ai_citation_check_workflow.json`**: sample answers → parse → rates with Wilson intervals → IF → alert.
- Result: 3/8 = 38% (95% CI 14%-69%).
- An empty answer is reported separately, not counted as "not cited".

**`analyze_with_python_service_workflow.json`**: n8n collects, then sends the answers to the Python API (`POST /analyze`).
- The service returned the same 3/8 and interval as the JavaScript version.

**`error_alert_workflow.json`**: Error Trigger → Code.
- It runs only for automatic (scheduled or webhook) executions, as the n8n docs say.

## Run them

1. Start n8n with Node.js 24+ (`npx n8n`) or Docker (`docker run -it --rm -p 5678:5678 docker.n8n.io/n8nio/n8n`).
2. Open `http://localhost:5678`, then *Workflows → Import from File*.
3. Set the site address in each workflow's *Config* node. For the Python-service workflow, start the API first: `uvicorn geo_tracker.api:app --port 8000`. In Docker, use `http://host.docker.internal:8000`.
4. To schedule a workflow, replace *Manual Trigger* with *Schedule Trigger*. To get alerts on failures, pick `error_alert_workflow` under *Settings → Error workflow* in the workflow you want watched.

## Traps found while testing

Details are in [../docs/FINDINGS.md](../docs/FINDINGS.md).
- `$pageCount` already counts the page just fetched. The off-by-one stop condition silently returned 2 of 3 posts.
- There is no `URL` class inside Code nodes, and `$env` is blocked in expressions in n8n 2.x.
- Response header names are lowercase (`x-wp-totalpages`).
- JavaScript's `\d` doesn't match full-width digits (`３０％`). Use `\p{Nd}` with the `u` flag.
