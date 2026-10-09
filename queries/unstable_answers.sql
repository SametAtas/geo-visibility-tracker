-- Keyword-brand pairs where the brand appeared in some runs of the same question but not others.
-- These are the cases where a single check could have reported either result.
SELECT collected_on, keyword, brand, runs_mentioning || '/' || runs AS runs
FROM keyword_brand
WHERE flips = 1
ORDER BY collected_on, keyword, runs_mentioning DESC;
