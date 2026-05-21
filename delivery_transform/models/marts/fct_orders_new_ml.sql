-- =============================================================
-- fct_orders_new_ml.sql  (MARTS — EXPERIMENTAL)
-- LAYER   : Marts
-- SOURCE  : staging.stg_orders
-- PURPOSE : New ML benchmark dataset.
--           Minimal filtering — keeps noisy/dirty rows.
--           DO NOT use in production DSS.
--           DO NOT replace fct_orders.sql.
-- =============================================================

{{ config(materialized='table') }}

-- ⚠️  EXPERIMENTAL ONLY — benchmark comparison against clean DSS model.

with base as (
    select * from {{ ref('stg_orders') }}
),

with_time_features as (
    select
        -- ── IDENTIFIER ───────────────────────────────────────
        order_id,

        -- ── TARGET ───────────────────────────────────────────
        delivery_time_min,

        -- ── CORE NUMERICAL FEATURES ──────────────────────────
        -- Raw distance (no bounds filtering — Kaggle-style)
        round(
            6371 * 2 * asin(sqrt(
                power(sin(radians((customer_lat - restaurant_lat) / 2)), 2)
                + cos(radians(restaurant_lat))
                * cos(radians(customer_lat))
                * power(sin(radians((customer_lon - restaurant_lon) / 2)), 2)
            ))::numeric,
            4
        )                                                   as distance_km,

        rider_rating,
        driver_age,
        (coalesce(multiple_deliveries, 1) + 1)::integer     as order_items,
        vehicle_condition,

        -- ── RAW COORDINATES (kept for reference) ─────────────
        restaurant_lat,
        restaurant_lon,
        customer_lat,
        customer_lon,

        -- ── CATEGORICAL FEATURES ─────────────────────────────
        case
            when traffic_raw = 'low'    then 'low'
            when traffic_raw = 'medium' then 'medium'
            when traffic_raw = 'high'   then 'high'
            when traffic_raw = 'jam'    then 'high'
            else                             'medium'
        end                                                 as traffic_level,

        case
            when weather_raw = 'sunny'                  then 'clear'
            when weather_raw in ('cloudy', 'windy')     then 'cloudy'
            when weather_raw in ('fog', 'sandstorms')   then 'rainy'
            when weather_raw = 'stormy'                 then 'stormy'
            else                                             'clear'
        end                                                 as weather,

        -- restaurant_type not in stg_orders — use order_type as proxy
        case
            when order_type in ('snack', 'drinks', 'buffet') then 'fast_food'
            when order_type = 'meal'                         then 'casual'
            else                                                  'fast_food'
        end                                                 as restaurant_type,

        vehicle_type,

        case
            when city_raw = 'Metropolitian' then 'Metropolitian'
            when city_raw = 'Urban'         then 'Urban'
            when city_raw = 'Semi-Urban'    then 'Semi-Urban'
            else                                 'Urban'
        end                                                 as city,

        -- ── KAGGLE-STYLE TIMESTAMP FEATURES ──────────────────
        -- Raw timestamps kept for feature derivation
        time_ordered,
        time_picked,

        -- Derived hour/minute from order time
        extract(hour   from time_ordered)::integer          as hour_order,
        extract(minute from time_ordered)::integer          as min_order,

        -- Derived hour/minute from pickup time
        extract(hour   from time_picked)::integer           as hour_order_picked,
        extract(minute from time_picked)::integer           as min_order_picked,

        -- pickup_delay_min: minutes between order placed and driver pickup
        -- Handles midnight rollover: if negative, add 1440 (24h in minutes)
        case
            when time_ordered is not null and time_picked is not null then
                case
                    when (
                        (extract(hour from time_picked)::integer * 60
                         + extract(minute from time_picked)::integer)
                        -
                        (extract(hour from time_ordered)::integer * 60
                         + extract(minute from time_ordered)::integer)
                    ) < 0
                    then (
                        (extract(hour from time_picked)::integer * 60
                         + extract(minute from time_picked)::integer)
                        -
                        (extract(hour from time_ordered)::integer * 60
                         + extract(minute from time_ordered)::integer)
                        + 1440
                    )
                    else (
                        (extract(hour from time_picked)::integer * 60
                         + extract(minute from time_picked)::integer)
                        -
                        (extract(hour from time_ordered)::integer * 60
                         + extract(minute from time_ordered)::integer)
                    )
                end
            else null
        end::numeric(7,2)                                   as pickup_delay_min

    from base
)

-- Minimal filter: only remove rows where target is missing
select * from with_time_features
where delivery_time_min is not null
