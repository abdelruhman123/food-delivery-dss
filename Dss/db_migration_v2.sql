-- =============================================================================
-- Migration v2 – Full System Integration
-- Run against: food_delivery  (PostgreSQL 13+, Port 5555)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. orders  – one row per customer order (header record)
--    Stores delivery address, ML travel prediction, and confirmed prep time.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    order_id              VARCHAR(50)   PRIMARY KEY,
    customer_address      TEXT          NOT NULL,
    latitude              NUMERIC(10,7) NOT NULL,
    longitude             NUMERIC(10,7) NOT NULL,
    restaurant_type       VARCHAR(50)   NOT NULL DEFAULT 'Fast Food',
    ml_travel_prediction  NUMERIC(6,2)  NULL,          -- minutes, from XGBoost
    confirmed_prep_time   NUMERIC(6,2)  NULL,          -- minutes, set by Chef
    total_eta             NUMERIC(6,2)  NULL,          -- confirmed_prep + ml_travel
    status                VARCHAR(20)   NOT NULL DEFAULT 'Pending'
                              CHECK (status IN ('Pending','Preparing','Ready','Delivered')),
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    confirmed_at          TIMESTAMPTZ   NULL
);

COMMENT ON TABLE  orders                       IS 'One row per customer order; links to live_orders item lines.';
COMMENT ON COLUMN orders.ml_travel_prediction  IS 'Delivery travel time predicted by the XGBoost ETA model (minutes).';
COMMENT ON COLUMN orders.confirmed_prep_time   IS 'Prep time confirmed by the Chef via kitchen_app (minutes).';
COMMENT ON COLUMN orders.total_eta             IS 'confirmed_prep_time + ml_travel_prediction (minutes).';

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);


-- -----------------------------------------------------------------------------
-- 2. live_orders – add order_id FK to the new orders header table
--    (safe to run multiple times – IF NOT EXISTS guards)
-- -----------------------------------------------------------------------------
ALTER TABLE live_orders
    ADD COLUMN IF NOT EXISTS suggested_prep_time NUMERIC(6,2) NULL,
    ADD COLUMN IF NOT EXISTS confirmed_prep_time NUMERIC(6,2) NULL;

COMMENT ON COLUMN live_orders.suggested_prep_time IS 'System-calculated prep time shown to Chef.';
COMMENT ON COLUMN live_orders.confirmed_prep_time IS 'Chef-confirmed prep time after human review.';

-- FK to orders header (add only if it does not already exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE  constraint_name = 'fk_live_orders_order_id'
          AND  table_name      = 'live_orders'
    ) THEN
        ALTER TABLE live_orders
            ADD CONSTRAINT fk_live_orders_order_id
            FOREIGN KEY (order_id) REFERENCES orders (order_id)
            ON DELETE CASCADE;
    END IF;
END $$;


-- -----------------------------------------------------------------------------
-- 3. Refresh station_metrics view (unchanged logic, re-create for safety)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW station_metrics AS
SELECT
    station_name,
    COUNT(*)                        AS active_items,
    SUM(remaining_time)             AS total_workload,
    ROUND(AVG(remaining_time), 2)   AS avg_remaining_time
FROM  live_orders
WHERE status IN ('Pending', 'Cooking')
GROUP BY station_name;


-- -----------------------------------------------------------------------------
-- 4. manager_order_view – denormalised view for the Manager Map DSS
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW manager_order_view AS
SELECT
    o.order_id,
    o.customer_address,
    o.latitude,
    o.longitude,
    o.restaurant_type,
    o.ml_travel_prediction,
    o.confirmed_prep_time,
    o.total_eta,
    o.status                        AS order_status,
    o.created_at,
    o.confirmed_at,
    COUNT(lo.id)                    AS total_items,
    SUM(CASE WHEN lo.status = 'Ready' THEN 1 ELSE 0 END) AS ready_items
FROM  orders     o
LEFT  JOIN live_orders lo USING (order_id)
GROUP BY o.order_id, o.customer_address, o.latitude, o.longitude,
         o.restaurant_type, o.ml_travel_prediction, o.confirmed_prep_time,
         o.total_eta, o.status, o.created_at, o.confirmed_at;

COMMENT ON VIEW manager_order_view IS
    'Denormalised order summary for the Manager Map DSS. '
    'Includes lat/lng, ML travel prediction, and Chef-confirmed prep time.';
