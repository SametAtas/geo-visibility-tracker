-- Mention rate per brand and period, with a 95% Wilson interval. Client first, then by rate.
SELECT collected_on, brand,
       mentioned || '/' || n AS mentioned,
       CAST(ROUND(100 * rate) AS INTEGER) || '%' AS rate,      -- not printf('%.0f'): SQLite's printf truncates 26.7 to 26
       CAST(ROUND(100 * ci_low) AS INTEGER) || '%-' || CAST(ROUND(100 * ci_high) AS INTEGER) || '%' AS ci95
FROM mention_rate_ci
ORDER BY collected_on, is_client DESC, rate DESC, brand;
