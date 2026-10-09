-- Do two engines recommend the same brands for the same question?
-- A brand is an engine's answer to a question when it appears in more than half of that engine's runs.
-- Agreement is the Jaccard overlap of those sets: 100% = same brands, 0% = nothing in common.
WITH majority AS (
    SELECT engine, keyword, brand FROM keyword_brand WHERE runs_mentioning * 2 > runs
),
engine_pair AS (
    SELECT DISTINCT a.engine AS engine_a, b.engine AS engine_b, a.keyword
    FROM keyword_brand a JOIN keyword_brand b ON a.keyword = b.keyword AND a.engine < b.engine
),
counts AS (
    SELECT p.engine_a, p.engine_b, p.keyword,
           (SELECT COUNT(*) FROM majority x JOIN majority y ON x.brand = y.brand AND x.keyword = y.keyword
             WHERE x.engine = p.engine_a AND y.engine = p.engine_b AND x.keyword = p.keyword) AS shared,
           (SELECT COUNT(DISTINCT brand) FROM majority z
             WHERE z.keyword = p.keyword AND z.engine IN (p.engine_a, p.engine_b)) AS combined
    FROM engine_pair p
)
SELECT engine_a, engine_b, keyword,
       shared || '/' || combined AS shared_brands,
       CASE WHEN combined = 0 THEN NULL ELSE CAST(ROUND(100.0 * shared / combined) AS INTEGER) || '%' END AS agreement
FROM counts
ORDER BY engine_a, engine_b, keyword;
