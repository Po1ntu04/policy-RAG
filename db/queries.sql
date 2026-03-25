-- Common queries for reporting, auditing, and performance tests.

-- 1) Indicator list by year and responsible org
SELECT
    i.indicator_id,
    i.year,
    i.primary_category,
    i.secondary_indicator,
    i.score,
    i.completion_status,
    o.org_name AS responsible_org
FROM indicators i
JOIN indicator_responsibilities r
    ON r.indicator_id = i.indicator_id
JOIN orgs o
    ON o.org_id = r.org_id
WHERE i.year = 2023
  AND r.duty_type = 'responsible_unit'
ORDER BY i.primary_category, i.secondary_indicator;

-- 2) Status statistics
SELECT completion_status, COUNT(*) AS cnt
FROM indicators
GROUP BY completion_status
ORDER BY cnt DESC;

-- 3) Audit report view (indicator + latest audit)
SELECT
    i.indicator_id,
    i.secondary_indicator,
    i.score,
    a.judgment,
    a.review_at,
    u.username AS reviewer
FROM indicators i
LEFT JOIN LATERAL (
    SELECT *
    FROM audit_records ar
    WHERE ar.indicator_id = i.indicator_id
    ORDER BY ar.review_at DESC
    LIMIT 1
) a ON TRUE
LEFT JOIN app_users u ON u.user_id = a.reviewer_user_id
WHERE i.year = 2023;

-- 4) Update completion status (CRUD example)
UPDATE indicators
SET completion_status = 'in_progress', updated_at = now(), version = version + 1
WHERE indicator_id = '00000000-0000-0000-0000-000000000000';

-- 5) Performance test: filter by year + status
EXPLAIN ANALYZE
SELECT *
FROM indicators
WHERE year = 2023
  AND completion_status = 'completed'
ORDER BY primary_category
LIMIT 100;
