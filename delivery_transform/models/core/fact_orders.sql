-- =============================================================
-- fact_orders.sql
-- LAYER   : Core
-- SOURCE  : stg_orders + dim_driver + dim_restaurant
-- PURPOSE : One row per order. Join all dimensions.
--           Engineer prep_time_min from timestamps.
--           Impute remaining nulls.
--           Apply 3-layer data quality flags.
-- =============================================================

-- depends_on: {{ ref('stg_orders') }}
with stg as (
    select * from {{ ref('stg_orders') }}
),

drivers as (
    select * from {{ ref('dim_driver') }}
),

restaurant as (
    select * from {{ ref('dim_restaurant') }}
),

-- ── NULL IMPUTATION ──────────────────────────────────────────
-- traffic_raw  : 601 nulls  → mode = 'low'
-- festival_raw : 228 nulls  → mode = 'no'
-- city_raw     : 1200 nulls → mode = 'metropolitian'
-- time_ordered : 1731 nulls → prep_time will be null, handled below
-- multiple_del : 993 nulls  → mode = 1

joined as (
    select
        -- ── Keys ─────────────────────────────────────────────
        s.order_id,
        s.driver_id,

        -- ── Driver features (from dim_driver — nulls already imputed) ─
        d.rider_rating,
        d.driver_age,
        d.vehicle_type,

        -- ── vehicle_condition from staging (not in dim_driver) ───
        s.vehicle_condition,

        -- ── Order metadata ───────────────────────────────────
        s.order_date,
        s.order_type,
        r.restaurant_type,

        -- city: impute NaN/null with mode (Metropolitian)
        case
            when s.city_raw is null
              or trim(s.city_raw) = 'NaN'
              or trim(s.city_raw) = ''
            then 'Metropolitian'
            else trim(s.city_raw)
        end                                         as city,

        -- area_density: derived from city directly in fact_orders
        -- NOT from dim_restaurant (caused 4x row multiplication)
        case
            when trim(coalesce(s.city_raw, 'Metropolitian')) = 'Metropolitian' then 'high'
            when trim(coalesce(s.city_raw, 'Metropolitian')) = 'Urban'         then 'medium'
            when trim(coalesce(s.city_raw, 'Metropolitian')) = 'Semi-Urban'    then 'low'
            else                                                                     'medium'
        end                                         as area_density,

        -- Impute multiple_deliveries null with mode (1)
        coalesce(s.multiple_deliveries, 1)          as multiple_deliveries,

        -- ── Coordinates ──────────────────────────────────────
        s.restaurant_lat,
        s.restaurant_lon,
        s.customer_lat,
        s.customer_lon,

        -- ── Timestamps ───────────────────────────────────────
        s.time_ordered,
        s.time_picked,

        -- ── Weather (impute null with mode = 'sunny') ────────
        coalesce(s.weather_raw, 'sunny')            as weather_raw,

        -- ── Traffic (impute null with mode = 'low') ──────────
        coalesce(s.traffic_raw, 'low')              as traffic_raw,

        -- ── Festival (impute null with mode = 'no') ──────────
        coalesce(s.festival_raw, 'no')              as festival_raw,

        -- ── Target ───────────────────────────────────────────
        s.delivery_time_min

    from stg s
    left join drivers d     on trim(s.driver_id) = trim(d.driver_id)
    left join restaurant r  on s.order_type      = r.order_type
),

-- ── PREP TIME ENGINEERING ─────────────────────────────────────
-- prep_time = minutes between order placed and driver pickup
-- time_ordered: 1731 nulls → fallback to rule-based estimate
-- Note: this is for ANALYTICS only — NOT used as ML feature
-- (as decided: backend_logic.py handles prep time at inference)

with_prep as (
    select
        *,

        case
            -- When both timestamps available: calculate real prep time
            -- Cast TIME to INTERVAL first to avoid PostgreSQL TIME subtraction issues
            when time_ordered is not null and time_picked is not null then
                case
                    when time_picked >= time_ordered then
                        extract(epoch from (
                            time_picked::interval - time_ordered::interval
                        )) / 60
                    else
                        -- Midnight crossover: add 24 hours to picked time
                        extract(epoch from (
                            time_picked::interval + interval '24 hours' - time_ordered::interval
                        )) / 60
                end

            -- Fallback: rule-based estimate by restaurant_type
            when restaurant_type = 'fast_food' then 10.0
            when restaurant_type = 'cafe'      then 12.0
            when restaurant_type = 'casual'    then 18.0
            when restaurant_type = 'fine_dine' then 28.0
            else                                    14.0
        end                                         as prep_time_min

    from joined
),

-- ── 3-LAYER DATA QUALITY FLAGS ───────────────────────────────

validated as (
    select
        *,

        -- LAYER 1: Corrupted coordinates
        -- 3,640 rows have Restaurant_lat = 0 (impossible for India)
        case
            when restaurant_lat = 0
              or restaurant_lon = 0
              or customer_lat   = 0
              or customer_lon   = 0
            then true
            else false
        end                                         as is_corrupted_coords,

        -- LAYER 2: Impossible delivery time
        case
            when delivery_time_min <= 0
              or delivery_time_min > 240
              or delivery_time_min is null
            then true
            else false
        end                                         as is_invalid_time,

        -- LAYER 3: Impossible speed
        -- Calculate distance via Haversine approximation in SQL
        -- Using simplified flat-earth formula for short distances
        case
            when delivery_time_min > 0
              and restaurant_lat != 0
              and customer_lat   != 0
            then
                round(
                    (
                        6371 * acos(
                            least(1.0, cos(radians(restaurant_lat))
                            * cos(radians(customer_lat))
                            * cos(radians(customer_lon) - radians(restaurant_lon))
                            + sin(radians(restaurant_lat))
                            * sin(radians(customer_lat)))
                        )
                    )::numeric, 4
                )
            else null
        end                                         as distance_km_raw,

        case
            when delivery_time_min > 0
              and restaurant_lat != 0
              and customer_lat   != 0
            then
                round(
                    (
                        6371 * acos(
                            least(1.0, cos(radians(restaurant_lat))
                            * cos(radians(customer_lat))
                            * cos(radians(customer_lon) - radians(restaurant_lon))
                            + sin(radians(restaurant_lat))
                            * sin(radians(customer_lat)))
                        )
                        / delivery_time_min * 60
                    )::numeric, 2
                )
            else null
        end                                         as avg_speed_kmh

    from with_prep
)

select
    *,
    -- Overall quality flag: row is clean if ALL 3 layers pass
    case
        when is_corrupted_coords = false
         and is_invalid_time     = false
         and (avg_speed_kmh is null or (avg_speed_kmh between 1 and 120))
        then true
        else false
    end                                             as is_valid_row

from validated