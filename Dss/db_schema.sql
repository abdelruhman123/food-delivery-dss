-- =============================================================================
-- Food Delivery DSS – Operational Database Schema
-- PostgreSQL 13+  |  Port 5555
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. kitchen_staffing
--    One row per station; updated by the Kitchen Manager via Streamlit.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kitchen_staffing (
    station_name  VARCHAR(50)  PRIMARY KEY,
    chef_count    INTEGER      NOT NULL CHECK (chef_count >= 0),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  kitchen_staffing              IS 'Active chef headcount per kitchen station.';
COMMENT ON COLUMN kitchen_staffing.station_name IS 'Unique station identifier (e.g. grill, fryer).';
COMMENT ON COLUMN kitchen_staffing.chef_count   IS 'Number of chefs currently active on this station.';
COMMENT ON COLUMN kitchen_staffing.updated_at   IS 'Timestamp of the last staffing update.';


-- -----------------------------------------------------------------------------
-- 2. live_orders
--    One row per item line in an active order; drives real-time workload.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS live_orders (
    id                  SERIAL       PRIMARY KEY,
    order_id            VARCHAR(50)  NOT NULL,
    item_name           VARCHAR(100) NOT NULL,
    station_name        VARCHAR(50)  NOT NULL
                            REFERENCES kitchen_staffing (station_name)
                            ON UPDATE CASCADE ON DELETE RESTRICT,
    quantity            INTEGER      NOT NULL CHECK (quantity > 0),
    prep_time_assigned  NUMERIC(6,2) NOT NULL CHECK (prep_time_assigned >= 0),
    remaining_time      NUMERIC(6,2) NOT NULL CHECK (remaining_time >= 0),
    status              VARCHAR(20)  NOT NULL DEFAULT 'Pending'
                            CHECK (status IN ('Pending', 'Cooking', 'Ready')),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  live_orders                    IS 'Item-level tracking for every order currently in the kitchen.';
COMMENT ON COLUMN live_orders.order_id           IS 'Business-level order reference (groups multiple items).';
COMMENT ON COLUMN live_orders.prep_time_assigned IS 'Estimated prep time (minutes) assigned at order creation.';
COMMENT ON COLUMN live_orders.remaining_time     IS 'Minutes of prep work still outstanding (updated by backend).';
COMMENT ON COLUMN live_orders.status             IS 'Lifecycle state: Pending → Cooking → Ready.';

-- Index for the workload aggregation query (hot path)
CREATE INDEX IF NOT EXISTS idx_live_orders_station_status
    ON live_orders (station_name, status);


-- -----------------------------------------------------------------------------
-- 3. station_metrics  (view)
--    Total remaining workload per station across all non-Ready orders.
--    Python backend fetches this to build the station_workload dict.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW station_metrics AS
SELECT
    station_name,
    COUNT(*)                        AS active_items,
    SUM(remaining_time)             AS total_workload,   -- input for calculate_prep_time()
    ROUND(AVG(remaining_time), 2)   AS avg_remaining_time
FROM  live_orders
WHERE status IN ('Pending', 'Cooking')
GROUP BY station_name;

COMMENT ON VIEW station_metrics IS
    'Aggregated kitchen workload per station (excludes Ready items). '
    'Used by the Python backend to populate station_workload.';
