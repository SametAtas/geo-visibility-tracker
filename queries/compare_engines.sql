-- The same questions, different AI engines: how often each one names each brand.
-- One row per brand and engine; read down a brand to compare engines.
SELECT brand, engine,
       mentioned || '/' || n AS mentioned,
       CAST(ROUND(100 * rate) AS INTEGER) || '%' AS rate,
       CAST(ROUND(100 * ci_low) AS INTEGER) || '%-' || CAST(ROUND(100 * ci_high) AS INTEGER) || '%' AS ci95
FROM mention_rate_ci
ORDER BY brand, rate DESC, engine;
