-- =============================================================================
-- Food Delivery DSS – Operational Queries
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1: station_workload dict  (primary input for calculate_prep_time)
--     Returns one row per active station; Python reads this into a dict.
-- -----------------------------------------------------------------------------
SELECT
    station_name,
    total_workload          -- SUM(remaining_time) for Pending + Cooking items
FROM  station_metrics
ORDER BY total_workload DESC;


-- -----------------------------------------------------------------------------
-- Q2: chef count per station  (for dynamic staffing lookup)
-- -----------------------------------------------------------------------------
SELECT station_name, chef_count
FROM   kitchen_staffing
ORDER  BY station_name;


-- -----------------------------------------------------------------------------
-- Q3: full live order board  (Streamlit kitchen display)
-- -----------------------------------------------------------------------------
SELECT
    lo.order_id,
    lo.item_name,
    lo.station_name,
    lo.quantity,
    lo.prep_time_assigned,
    lo.remaining_time,
    lo.status,
    ks.chef_count,
    lo.created_at
FROM  live_orders      lo
JOIN  kitchen_staffing ks USING (station_name)
ORDER BY lo.created_at DESC, lo.order_id, lo.station_name;


-- -----------------------------------------------------------------------------
-- Q4: mark an item as Ready  (called by backend when timer expires)
-- -----------------------------------------------------------------------------
-- UPDATE live_orders
-- SET    status = 'Ready', remaining_time = 0
-- WHERE  order_id = 'ORD-001' AND item_name = 'Burger';


-- -----------------------------------------------------------------------------
-- Q5: update remaining_time tick  (called every N seconds by the backend)
-- -----------------------------------------------------------------------------
-- UPDATE live_orders
-- SET    remaining_time = GREATEST(remaining_time - :elapsed_seconds / 60.0, 0),
--        status = CASE
--                     WHEN remaining_time - :elapsed_seconds / 60.0 <= 0 THEN 'Ready'
--                     WHEN status = 'Pending'                             THEN 'Cooking'
--                     ELSE status
--                 END
-- WHERE  status != 'Ready';
