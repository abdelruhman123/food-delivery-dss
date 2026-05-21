-- =============================================================
-- stg_orders.sql
-- LAYER   : Staging
-- SOURCE  : public.raw_deliveries
-- PURPOSE : Rename columns, cast types, extract values from
--           dirty formats. NO business logic — only cleaning.
-- NOTE    : Data has no string NaN literals and no real NULLs.
--           Only empty string checks needed as safety net.
-- =============================================================

with source as (
    select * from {{ source('public', 'raw_deliveries') }}
),

cleaned as (
    select
        -- ── IDs ──────────────────────────────────────────────
        trim(id)                                            as order_id,
        trim(delivery_person_id)                            as driver_id,

        -- ── Driver attributes ────────────────────────────────
        case
            when trim(delivery_person_age) = ''
              or trim(delivery_person_age) = 'NaN'
              or delivery_person_age is null
            then null
            else trim(delivery_person_age)::integer
        end                                                 as driver_age,

        case
            when trim(delivery_person_ratings) = ''
              or trim(delivery_person_ratings) = 'NaN'
              or delivery_person_ratings is null
            then null
            else trim(delivery_person_ratings)::numeric(3,1)
        end                                                 as rider_rating,

        -- ── Coordinates ──────────────────────────────────────
        restaurant_latitude::numeric(10,6)                  as restaurant_lat,
        restaurant_longitude::numeric(10,6)                 as restaurant_lon,
        delivery_location_latitude::numeric(10,6)           as customer_lat,
        delivery_location_longitude::numeric(10,6)          as customer_lon,

        -- ── Timestamps ───────────────────────────────────────
        to_date(order_date, 'DD-MM-YYYY')                   as order_date,

        case
            when trim(time_orderd) = ''
              or trim(time_orderd) = 'NaN'
              or time_orderd is null
            then null
            else trim(time_orderd)::time
        end                                                 as time_ordered,

        case
            when trim(time_order_picked) = ''
              or trim(time_order_picked) = 'NaN'
              or time_order_picked is null
            then null
            else trim(time_order_picked)::time
        end                                                 as time_picked,

        -- ── Weather ──────────────────────────────────────────
        -- Raw: "conditions Sunny" → extract word after space → "sunny"
        lower(trim(split_part(weatherconditions, ' ', 2)))  as weather_raw,

        -- ── Traffic ──────────────────────────────────────────
        lower(trim(road_traffic_density))                   as traffic_raw,

        -- ── Vehicle ──────────────────────────────────────────
        -- vehicle_condition is INTEGER in postgres — no cast needed
        vehicle_condition                                   as vehicle_condition,
        lower(trim(type_of_vehicle))                        as vehicle_type,

        -- ── Order ────────────────────────────────────────────
        lower(trim(type_of_order))                          as order_type,

        case
            when trim(multiple_deliveries) = ''
              or trim(multiple_deliveries) = 'NaN'
              or multiple_deliveries is null
            then null
            else trim(multiple_deliveries)::integer
        end                                                 as multiple_deliveries,

        -- ── Festival ─────────────────────────────────────────
        lower(trim(festival))                               as festival_raw,

        -- ── City ─────────────────────────────────────────────
        trim(city)                                          as city_raw,

        -- ── Target variable ──────────────────────────────────
        -- Raw: "(min) 24" → split on space → take part 2 → cast integer
        trim(split_part(time_taken_min, ' ', 2))::integer   as delivery_time_min

    from source
)

select * from cleaned
