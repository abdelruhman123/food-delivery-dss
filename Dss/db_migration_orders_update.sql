-- ============================================================================
-- Migration: Update orders table for ML feature completeness + Data Validation Layer
-- Purpose: Add traffic data, API fallback flag, validation flags, and ensure all ML features
-- Author: Food Delivery DSS Team
-- Date: 2024
-- ============================================================================

-- Add new columns to orders table if they don't exist
ALTER TABLE orders 
    ADD COLUMN IF NOT EXISTS traffic_ratio DECIMAL(5, 3),
    ADD COLUMN IF NOT EXISTS traffic_level VARCHAR(20) CHECK (traffic_level IN ('low', 'medium', 'high')),
    ADD COLUMN IF NOT EXISTS is_api_fallback BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS distance_km DECIMAL(10, 3),
    ADD COLUMN IF NOT EXISTS prep_time_min DECIMAL(10, 2),
    ADD COLUMN IF NOT EXISTS delivery_time_min DECIMAL(10, 2),
    ADD COLUMN IF NOT EXISTS rider_rating DECIMAL(3, 2),
    ADD COLUMN IF NOT EXISTS weather_encoded DECIMAL(5, 2),
    ADD COLUMN IF NOT EXISTS is_rainy DECIMAL(1, 0) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS hour_of_day DECIMAL(2, 0),
    ADD COLUMN IF NOT EXISTS day_of_week DECIMAL(1, 0),
    ADD COLUMN IF NOT EXISTS is_holiday DECIMAL(1, 0) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS order_items DECIMAL(5, 0),
    ADD COLUMN IF NOT EXISTS pickup_to_hub_km DECIMAL(10, 3),
    ADD COLUMN IF NOT EXISTS weather VARCHAR(20) CHECK (weather IN ('clear', 'cloudy', 'rainy', 'stormy')),
    ADD COLUMN IF NOT EXISTS area_density VARCHAR(20) CHECK (area_density IN ('residential', 'commercial', 'mixed', 'unknown')),
    
    -- DATA VALIDATION FLAGS (NEW - STEP 2)
    ADD COLUMN IF NOT EXISTS is_corrupted BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_impossible_speed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS validation_notes TEXT;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_orders_traffic_level ON orders(traffic_level);
CREATE INDEX IF NOT EXISTS idx_orders_area_density ON orders(area_density);
CREATE INDEX IF NOT EXISTS idx_orders_is_api_fallback ON orders(is_api_fallback);
CREATE INDEX IF NOT EXISTS idx_orders_is_corrupted ON orders(is_corrupted);
CREATE INDEX IF NOT EXISTS idx_orders_is_impossible_speed ON orders(is_impossible_speed);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_restaurant_type ON orders(restaurant_type);

-- Add comments for documentation
COMMENT ON COLUMN orders.traffic_ratio IS 'Raw traffic ratio from Google API: duration_in_traffic / duration. Used to derive traffic_level.';
COMMENT ON COLUMN orders.traffic_level IS 'Categorical traffic level: low (<1.15), medium (1.15-1.35), high (>1.35). PRIMARY ML FEATURE.';
COMMENT ON COLUMN orders.is_api_fallback IS 'TRUE if Google API failed and fallback values were used. Exclude from ML training.';
COMMENT ON COLUMN orders.distance_km IS 'Road distance from Google Directions API (or Haversine fallback if API failed).';
COMMENT ON COLUMN orders.prep_time_min IS 'Dynamic preparation time from backend_logic.py (NOT static base time). PRIMARY ML FEATURE.';
COMMENT ON COLUMN orders.delivery_time_min IS 'Actual delivery time in minutes. TARGET VARIABLE for ML model.';
COMMENT ON COLUMN orders.area_density IS 'Area type from zones table lookup: residential, commercial, mixed, unknown. PRIMARY ML FEATURE.';
COMMENT ON COLUMN orders.is_corrupted IS 'TRUE if data has negative/zero/NULL critical values. Flagged but NOT deleted.';
COMMENT ON COLUMN orders.is_impossible_speed IS 'TRUE if avg_speed_kmh > 120 or < 1 (with distance > 2km). Flagged but NOT deleted.';
COMMENT ON COLUMN orders.validation_notes IS 'Human-readable notes about data quality issues for auditing.';

-- Create view for ML-ready data (3-layer validation approach)
CREATE OR REPLACE VIEW ml_training_data AS
SELECT 
    order_id,
    delivery_time_min,
    distance_km,
    prep_time_min,
    rider_rating,
    weather_encoded,
    is_rainy,
    hour_of_day,
    day_of_week,
    is_holiday,
    order_items,
    pickup_to_hub_km,
    traffic_level,
    weather,
    restaurant_type,
    area_density,
    created_at,
    
    -- Validation flags (for transparency)
    is_api_fallback,
    is_corrupted,
    is_impossible_speed
FROM orders
WHERE 
    -- LAYER 1: Exclude API fallback data (unreliable)
    is_api_fallback = FALSE
    
    -- LAYER 2: Exclude corrupted data (negative/zero/NULL)
    AND is_corrupted = FALSE
    
    -- LAYER 3: Keep impossible speed data (flag only, don't exclude)
    -- Note: is_impossible_speed is kept for model to learn from
    
    -- Ensure critical features exist
    AND distance_km IS NOT NULL
    AND prep_time_min IS NOT NULL
    AND delivery_time_min IS NOT NULL
    AND traffic_level IS NOT NULL
    AND area_density IS NOT NULL;

COMMENT ON VIEW ml_training_data IS 'Clean, ML-ready data excluding API fallback and corrupted rows. Keeps real-world outliers (long distance, long duration, impossible speed) for model learning.';

-- Create full audit view (includes ALL data with flags)
CREATE OR REPLACE VIEW data_audit_full AS
SELECT 
    order_id,
    delivery_time_min,
    distance_km,
    prep_time_min,
    traffic_level,
    area_density,
    created_at,
    
    -- Validation flags
    is_api_fallback,
    is_corrupted,
    is_impossible_speed,
    validation_notes,
    
    -- Derived metrics for analysis
    CASE 
        WHEN delivery_time_min > 0 THEN 
            ROUND((distance_km / delivery_time_min * 60)::NUMERIC, 2)
        ELSE NULL
    END AS avg_speed_kmh,
    
    -- Data quality category
    CASE
        WHEN is_corrupted THEN 'corrupted'
        WHEN is_api_fallback THEN 'api_fallback'
        WHEN is_impossible_speed THEN 'impossible_speed'
        ELSE 'valid'
    END AS data_quality_category
    
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY created_at DESC;

COMMENT ON VIEW data_audit_full IS 'Full audit trail of all orders with validation flags. Use for data quality monitoring and debugging.';

-- Create summary statistics view
CREATE OR REPLACE VIEW data_quality_summary AS
SELECT 
    COUNT(*) AS total_orders,
    
    -- Layer 1: API fallback
    SUM(CASE WHEN is_api_fallback = TRUE THEN 1 ELSE 0 END) AS api_fallback_count,
    ROUND(100.0 * SUM(CASE WHEN is_api_fallback = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) AS api_fallback_pct,
    
    -- Layer 2: Corrupted data
    SUM(CASE WHEN is_corrupted = TRUE THEN 1 ELSE 0 END) AS corrupted_count,
    ROUND(100.0 * SUM(CASE WHEN is_corrupted = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) AS corrupted_pct,
    
    -- Layer 3: Impossible speed (flagged but kept)
    SUM(CASE WHEN is_impossible_speed = TRUE THEN 1 ELSE 0 END) AS impossible_speed_count,
    ROUND(100.0 * SUM(CASE WHEN is_impossible_speed = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) AS impossible_speed_pct,
    
    -- Valid for ML training
    SUM(CASE WHEN is_api_fallback = FALSE AND is_corrupted = FALSE THEN 1 ELSE 0 END) AS ml_ready_count,
    ROUND(100.0 * SUM(CASE WHEN is_api_fallback = FALSE AND is_corrupted = FALSE THEN 1 ELSE 0 END) / COUNT(*), 2) AS ml_ready_pct,
    
    -- Statistics on valid data only
    ROUND(AVG(CASE WHEN is_api_fallback = FALSE AND is_corrupted = FALSE THEN distance_km END), 2) AS avg_distance_km,
    ROUND(AVG(CASE WHEN is_api_fallback = FALSE AND is_corrupted = FALSE THEN prep_time_min END), 2) AS avg_prep_time_min,
    ROUND(AVG(CASE WHEN is_api_fallback = FALSE AND is_corrupted = FALSE THEN delivery_time_min END), 2) AS avg_delivery_time_min,
    
    -- Categorical feature distribution
    COUNT(DISTINCT traffic_level) AS unique_traffic_levels,
    COUNT(DISTINCT area_density) AS unique_area_densities
    
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';

COMMENT ON VIEW data_quality_summary IS 'Summary statistics for data quality monitoring (last 30 days). Shows 3-layer validation approach.';
