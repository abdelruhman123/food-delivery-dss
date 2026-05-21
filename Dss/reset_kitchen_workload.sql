-- =============================================================================
-- reset_kitchen_workload.sql
-- Food Delivery DSS — Operational Data Reset
-- =============================================================================
-- PURPOSE:
--   Remove seeded / accumulated demo operational rows from live_orders and
--   orders that are inflating station_workload and causing unrealistic
--   prep time suggestions.
--
-- WHAT THIS TOUCHES:
--   live_orders   — truncated (all item-level rows removed)
--   orders        — truncated (all order header rows removed)
--
-- WHAT THIS PRESERVES:
--   kitchen_staffing    — chef headcounts kept (correct configuration)
--   zones               — area density lookup data kept
--   raw_deliveries      — ML training data kept
--   All schema objects  — tables, views, functions, indexes kept
--   dbt artifacts       — not touched
--   ML artifacts        — not touched
--
-- WHY THIS FIXES THE PREP TIME BUG:
--   station_metrics view sums remaining_time for all non-Ready rows in
--   live_orders. The seed file inserted 7 demo rows with remaining_time
--   values of 1–18 min each, all in 'Pending' or 'Cooking' status.
--   These rows were never cleared, so every new order saw:
--     grill workload  = 12 + 18 = 30 min  (ORD-001 + ORD-002)
--     fryer workload  = 5 min
--     saute workload  = 10 min
--     espresso workload = 3 min
--     bakery workload = 3 min
--   With OVERLAP_FACTOR=1.2 and CONGESTION_PENALTY kicking in at 30 min,
--   a simple 2x Burger order (base 7 min each) was seeing:
--     queue_time = (30 / 2 chefs) * 1.2 = 18 min
--     congestion_penalty = ((30-30)/30) * 0.15 * 30 = 0 min (right at threshold)
--     production_time = 7 * 2 = 14 min
--     total = 18 + 14 = 32 min per item
--   Any additional accumulated test orders pushed grill workload well above
--   30 min, triggering the congestion penalty and producing 100+ min estimates.
--
-- RUN:
--   psql -U root -d food_delivery -h localhost -p 5555 -f Dss/reset_kitchen_workload.sql
-- =============================================================================

BEGIN;

-- Step 1: Remove all item-level operational rows
--         CASCADE is not needed here; live_orders has no dependents.
TRUNCATE TABLE live_orders RESTART IDENTITY;

-- Step 2: Remove all order header rows
--         live_orders FK references orders, but we truncated live_orders first.
TRUNCATE TABLE orders RESTART IDENTITY CASCADE;

-- Step 3: Verify station_metrics is now empty (workload = 0 for all stations)
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN '✓ station_metrics is empty — workload reset to zero'
        ELSE '✗ WARNING: station_metrics still has rows — check live_orders'
    END AS verification
FROM station_metrics;

COMMIT;

-- =============================================================================
-- EXPECTED OUTPUT after running:
--   TRUNCATE TABLE
--   TRUNCATE TABLE
--   verification
--   ─────────────────────────────────────────────────────────────────
--   ✓ station_metrics is empty — workload reset to zero
-- =============================================================================
