-- The sites AI answers link to most: often third-party pages, which are where to earn coverage.
SELECT collected_on, domain, answers
FROM cited_domain_count
ORDER BY collected_on, answers DESC, domain
LIMIT 20;
