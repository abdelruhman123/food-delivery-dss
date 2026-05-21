-- =============================================================
-- fct_orders.sql  (MARTS)
-- LAYER   : Marts
-- SOURCE  : core.fact_orders
-- PURPOSE : Final analytics + ML-ready table.
--           Engineers all 23 ML features + prep_time_min
--           (analytics only).
--           Only CLEAN rows pass through (is_valid_row = true).
-- =============================================================

-- depends_on: {{ ref('fact_orders') }}
with core as (
    select * from {{ ref('fact_orders') }}
    where is_valid_row = true
),

engineered as (
    select
        -- ══════════════════════════════════════════════════════
        -- IDENTIFIERS (not ML features)
        -- ══════════════════════════════════════════════════════
        order_id,
        driver_id,
        order_date,

        -- ══════════════════════════════════════════════════════
        -- NUMERICAL FEATURES (21)
        -- ══════════════════════════════════════════════════════

        -- 1. distance_km
        distance_km_raw                                     as distance_km,

        -- 2. log_distance
        round(ln(1 + distance_km_raw)::numeric, 4)         as log_distance,

        -- 3. rider_rating
        rider_rating::numeric(3,1)                          as rider_rating,

        -- 4. weather_encoded
        case
            when weather_raw = 'sunny'      then 0.0
            when weather_raw = 'cloudy'     then 1.0
            when weather_raw = 'windy'      then 1.5
            when weather_raw = 'fog'        then 2.0
            when weather_raw = 'sandstorms' then 2.0
            when weather_raw = 'stormy'     then 3.0
            else                                 1.0
        end::numeric(3,1)                                   as weather_encoded,

        -- 5. is_rainy
        case
            when weather_raw in ('stormy', 'fog', 'sandstorms') then 1.0
            else 0.0
        end::numeric(3,1)                                   as is_rainy,

        -- 6. hour_of_day
        extract(hour from time_ordered)::integer            as hour_of_day,

        -- 7. day_of_week
        extract(dow from order_date)::integer               as day_of_week,

        -- 8. is_holiday — Egyptian weekend Friday(5) + Saturday(6)
        case
            when extract(dow from order_date) in (5, 6) then 1.0
            else 0.0
        end::numeric(3,1)                                   as is_holiday,

        -- 9. is_weekend — Sunday(0) + Saturday(6)
        case
            when extract(dow from order_date) in (0, 6) then 1.0
            else 0.0
        end::numeric(3,1)                                   as is_weekend,

        -- 10. order_items
        (coalesce(multiple_deliveries, 1) + 1)::integer     as order_items,

        -- 11. pickup_to_hub_km
        case
            when city = 'Metropolitian' then 2.5
            when city = 'Urban'         then 1.8
            when city = 'Semi-Urban'    then 1.2
            else                             2.0
        end::numeric(4,2)                                   as pickup_to_hub_km,

        -- 12. is_long_distance
        case
            when distance_km_raw > 20 then 1.0
            else 0.0
        end::numeric(3,1)                                   as is_long_distance,

        -- 13. is_ramadan
        case
            when festival_raw = 'yes' then 1.0
            else 0.0
        end::numeric(3,1)                                   as is_ramadan,

        -- 14. driver_age
        driver_age::integer                                 as driver_age,

        -- 15. vehicle_condition — 0-3 score
        vehicle_condition::integer                          as vehicle_condition,

        -- 16. order_month — seasonal signal
        extract(month from order_date)::integer             as order_month,

        -- 17. order_day — day of month signal
        extract(day from order_date)::integer               as order_day,

        -- 18. min_order — minute of order placement
        extract(minute from time_ordered)::integer          as min_order,

        -- 19. hour_order_picked — hour when driver picked up order
        extract(hour from time_picked)::integer             as hour_order_picked,

        -- 20. min_order_picked — minute when driver picked up order
        extract(minute from time_picked)::integer           as min_order_picked,

        -- ══════════════════════════════════════════════════════
        -- CATEGORICAL FEATURES (6)
        -- ══════════════════════════════════════════════════════

        -- 17. traffic_level
        case
            when traffic_raw = 'low'    then 'low'
            when traffic_raw = 'medium' then 'medium'
            when traffic_raw = 'high'   then 'high'
            when traffic_raw = 'jam'    then 'high'
            else                             'medium'
        end                                                 as traffic_level,

        -- 18. weather
        case
            when weather_raw = 'sunny'                  then 'clear'
            when weather_raw in ('cloudy', 'windy')     then 'cloudy'
            when weather_raw in ('fog', 'sandstorms')   then 'rainy'
            when weather_raw = 'stormy'                 then 'stormy'
            else                                             'clear'
        end                                                 as weather,

        -- 19. restaurant_type
        restaurant_type,

        -- 20. city
        case
            when city = 'Metropolitian' then 'Metropolitian'
            when city = 'Urban'         then 'Urban'
            when city = 'Semi-Urban'    then 'Semi-Urban'
            else                             'Urban'
        end                                                 as city,

        -- 21. distance_category
        case
            when distance_km_raw <= 5  then 'local'
            when distance_km_raw <= 15 then 'city'
            when distance_km_raw <= 30 then 'long_range'
            else                            'extreme'
        end                                                 as distance_category,

        -- 22. vehicle_type
        vehicle_type,

        -- 23. city_code — extracted from driver_id
        --     e.g. BANGRES13DEL02 → BANG
        split_part(trim(driver_id), 'RES', 1)               as city_code,

        -- 24. order_prepare_time — fixed prep time from core (analytics + ML)
        prep_time_min                                       as order_prepare_time,

        -- 25. order_time_period — binned hour signal
        case
            when extract(hour from time_ordered) in (0,1,2,3,4,5)    then 'night'
            when extract(hour from time_ordered) in (6,7,8,9,10,11)  then 'morning'
            when extract(hour from time_ordered) in (12,13,14)        then 'noon'
            when extract(hour from time_ordered) in (15,16,17,18,19) then 'afternoon'
            else                                                            'evening'
        end                                                 as order_time_period,

        -- ══════════════════════════════════════════════════════
        -- TARGET VARIABLE
        -- ══════════════════════════════════════════════════════
        delivery_time_min::numeric(6,2)                     as delivery_time_min,

        -- ══════════════════════════════════════════════════════
        -- ANALYTICS ONLY — NOT ML FEATURES
        -- ══════════════════════════════════════════════════════
        prep_time_min::numeric(6,2)                         as prep_time_min,
        avg_speed_kmh,
        multiple_deliveries,
        festival_raw                                        as is_festival

    from core
    where distance_km_raw is not null
      and distance_km_raw > 0
)

select * from engineered
