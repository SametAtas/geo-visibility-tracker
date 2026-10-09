-- How each brand's mention rate moved since the previous period (window function LAG in the view).
-- A change is not proof: check it with the report's significance test before telling a client.
SELECT brand, previous_on, collected_on,
       CAST(ROUND(100 * change) AS INTEGER) AS change_points,
       mentioned || '/' || n AS now
FROM mention_change
WHERE previous_on IS NOT NULL
ORDER BY ABS(change) DESC, brand;
