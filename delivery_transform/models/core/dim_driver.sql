-- =============================================================
-- dim_driver.sql
-- LAYER   : Core
-- SOURCE  : stg_orders
-- PURPOSE : One row per driver. Impute missing age and rating
--           with median values. Derive city_code from driver ID.
-- NULL STRATEGY:
--   driver_age    → 1854 nulls → impute with median (32)
--   rider_rating  → 1908 nulls → impute with median (4.7)
-- =============================================================

-- depends_on: {{ ref('stg_orders') }}
with stg as (
    select * from {{ ref('stg_orders') }}
),

-- Compute medians from non-null rows to use for imputation
medians as (
    select
        percentile_cont(0.5) within group (order by driver_age)    as median_age,
        percentile_cont(0.5) within group (order by rider_rating)  as median_rating
    from stg
    where driver_age is not null
      and rider_rating is not null
),

drivers as (
    select distinct on (s.driver_id)
        s.driver_id,

        -- City code extracted from driver ID: "BANGRES13DEL02" → "BANG"
        split_part(trim(s.driver_id), 'RES', 1)        as city_code,

        -- Impute nulls with median
        coalesce(s.driver_age, m.median_age::integer)  as driver_age,
        coalesce(
            s.rider_rating,
            m.median_rating::numeric(3,1)
        )                                               as rider_rating,

        s.vehicle_type,
        s.vehicle_condition

    from stg s
    cross join medians m
    order by s.driver_id, s.order_date desc   -- keep most recent record per driver
)

select * from drivers
