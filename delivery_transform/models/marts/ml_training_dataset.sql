-- =============================================================
-- ml_training_dataset.sql  (MARTS)
-- LAYER   : Marts
-- SOURCE  : marts.fct_orders
-- PURPOSE : Single source of truth for ML training.
--           24 features + target. dbt ONLY — no Python engineering.
-- VERSION : 4.0.0
-- FEATURES:
--   Numerical (17): distance_km, log_distance, rider_rating,
--                   weather_encoded, is_rainy, hour_of_day,
--                   day_of_week, is_holiday, is_weekend,
--                   order_items, pickup_to_hub_km, is_long_distance,
--                   is_ramadan, driver_age, vehicle_condition,
--                   order_month, order_prepare_time
--   Categorical (7): traffic_level, weather, restaurant_type,
--                    city, distance_category, vehicle_type,
--                    order_time_period
-- =============================================================

{{ config(materialized='view') }}

-- depends_on: {{ ref('fct_orders') }}

select
    -- ── IDENTIFIER ───────────────────────────────────────────
    order_id,

    -- ── 17 NUMERICAL ─────────────────────────────────────────
    distance_km,
    log_distance,
    rider_rating,
    weather_encoded,
    is_rainy,
    hour_of_day,
    day_of_week,
    is_holiday,
    is_weekend,
    order_items,
    pickup_to_hub_km,
    is_long_distance,
    is_ramadan,
    driver_age,
    vehicle_condition,
    order_month,
    order_prepare_time,

    -- ── 7 CATEGORICAL ────────────────────────────────────────
    traffic_level,
    weather,
    restaurant_type,
    city,
    distance_category,
    vehicle_type,
    order_time_period,

    -- ── TARGET ───────────────────────────────────────────────
    delivery_time_min

    -- ── EXCLUDED ─────────────────────────────────────────────
    -- order_day, min_order, hour_order_picked, min_order_picked → reverted (v4.0.0)
    -- city_code          → no signal (all cities avg ~26 min)
    -- prep_time_min      → analytics alias
    -- avg_speed_kmh      → data leakage
    -- driver_id          → identifier

from {{ ref('fct_orders') }}

where distance_km          is not null
  and rider_rating         is not null
  and hour_of_day          is not null
  and driver_age           is not null
  and vehicle_condition    is not null
  and order_prepare_time   is not null
  and order_prepare_time   between 0 and 60
  and delivery_time_min    between 5 and 240
