-- How stable is each engine? For every question-brand pair the engine named at least once:
-- flips = named in some runs but not all; single-check error = chance one run disagrees with the majority.
SELECT engine,
       COUNT(*) AS pairs_seen,
       SUM(flips) AS pairs_flipping,
       CAST(ROUND(100.0 * SUM(flips) / COUNT(*)) AS INTEGER) || '%' AS flip_share,
       CAST(ROUND(100.0 * AVG(MIN(runs_mentioning, runs - runs_mentioning) * 1.0 / runs)) AS INTEGER) || '%' AS single_check_error
FROM keyword_brand
WHERE runs_mentioning > 0
GROUP BY engine
ORDER BY engine;
