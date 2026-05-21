# DATA_VALIDATION_LAYER (dbt - current)

This document reflects the current validation implemented in `delivery_transform/models/core/fact_orders.sql`.

## 3-layer validation in `fact_orders`

### Layer 1 — corrupted coordinates

- Criteria: restaurant/customer lat/lon = 0
- Flag: `is_corrupted_coords`
- Effect: excluded from clean marts
- Rows flagged: ~3,640

### Layer 2 — invalid delivery time

- Criteria: `delivery_time_min <= 0` or `delivery_time_min > 240` or null
- Flag: `is_invalid_time`
- Effect: excluded from clean marts

### Layer 3 — impossible speed

- Computed: `avg_speed_kmh`
- Criteria: `avg_speed_kmh > 120` (or other impossible bounds)
- Effect: excluded from clean marts via `is_valid_row`

## Final clean filter (marts)

`dbt_schema_marts.fct_orders` filters:

- `WHERE is_valid_row = true`

Result:
- **45,593 → 41,507 rows**
