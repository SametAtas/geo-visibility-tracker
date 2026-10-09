# Data flow

```mermaid
flowchart LR
    subgraph Sources
        K[keywords.txt] --> C
        API[(OpenAI-compatible API)] --> C
        R[(recorded answers .jsonl)] --> C
        WP[(WordPress REST API)] --> A
        F[forum titles .csv] --> Q
        T[AI-generated table .json] --> X
    end
    C[collect<br/>N runs per keyword<br/>rate limit, retries] -->|upsert per date, engine, keyword, run<br/>errors stored, not dropped| DB[(SQLite: raw answers)]
    DB --> P[parse<br/>normalize, mentions vs citations]
    P --> M[metrics<br/>Wilson 95% CI, share of voice,<br/>z-test vs previous period]
    M --> H[HTML report]
    M --> J[JSON / API /analyze]
    A[audit<br/>sources, statistics, quotes, FAQ] --> H
    Q[question mining<br/>clean, keep questions, group, intent] --> H
    X[fact-check<br/>evidence + numbers on cited page] --> H
    J --> N[n8n: schedule, alert, Error Trigger]
```

**Principles:**
- **Raw first.** Answers are stored exactly as received; every number is recomputed from them.
- **Idempotent.** A unique key plus upsert means re-running any day is safe.
- **Nothing disappears silently.** Empty answers and errors are stored and shown in the report's data-quality table.
- **Untrusted text.** Answers, configs and fetched pages are escaped before they reach HTML.
