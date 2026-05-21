-- =============================================================
-- dim_restaurant.sql
-- LAYER   : Core
-- SOURCE  : stg_orders
-- PURPOSE : Map order_type → restaurant_type ONLY.
--           4 rows — one per order type.
--           area_density and city handled in fact_orders directly.
-- =============================================================

-- depends_on: {{ ref('stg_orders') }}
with order_types as (
    select distinct order_type
    from {{ ref('stg_orders') }}
)

select
    order_type,

    -- Map Kaggle order types to your feature_contract values
    case
        when order_type = 'snack'  then 'fast_food'
        when order_type = 'meal'   then 'casual'
        when order_type = 'buffet' then 'fine_dine'
        when order_type = 'drinks' then 'cafe'
        else                             'casual'
    end as restaurant_type

from order_types
