# delivery_transform — dbt Project

## Layer Architecture

```
raw.train (Kaggle CSV loaded into PostgreSQL)
    │
    ▼
STAGING — stg_orders.sql
    • Rename all columns to snake_case
    • Cast all types (string → integer, float, date, time)
    • Handle string 'NaN' literals → real NULL
    • Strip "conditions " prefix from weather
    • Extract integer from "(min) 24" → 24
    │
    ▼
CORE ─────────────────────────────────────────────
    dim_driver.sql
        • One row per driver
        • Impute driver_age nulls → median (32)
        • Impute rider_rating nulls → median (4.7)
        • Extract city_code from driver ID

    dim_restaurant.sql
        • Map order_type → restaurant_type
          Snack→fast_food, Meal→casual, Buffet→fine_dine, Drinks→cafe
        • Map city → area_density
          Metropolitian→high, Urban→medium, Semi-Urban→low

    fact_orders.sql
        • Join stg_orders + dim_driver + dim_restaurant
        • Impute traffic nulls → 'low' (mode)
        • Impute festival nulls → 'no' (mode)
        • Impute city nulls → 'Metropolitian' (mode)
        • Engineer prep_time_min from timestamps
          (fallback to rule-based when time_ordered is null)
        • Calculate Haversine distance_km
        • Calculate avg_speed_kmh
        • Apply 3-layer quality flags:
            Layer 1: is_corrupted_coords (zero lat/lon)
            Layer 2: is_invalid_time (<=0 or >240 min)
            Layer 3: impossible speed (>120 km/h)
    │
    ▼
MARTS ────────────────────────────────────────────
    fct_orders.sql (TABLE)
        • Only valid rows (is_valid_row = true)
        • Engineers all 17 ML features
        • Keeps prep_time_min for analytics ONLY
        • Source for dashboards + manager Streamlit

    ml_training_dataset.sql (VIEW on fct_orders)
        • Exactly 17 features + delivery_time_min target
        • prep_time_min excluded
        • avg_speed_kmh excluded (data leakage)
        • Source for ml_models_enhanced.py ONLY
```

## Null Handling Summary

| Column | Nulls | Strategy |
|---|---|---|
| driver_age | 1,854 | Impute median (32) in dim_driver |
| rider_rating | 1,908 | Impute median (4.7) in dim_driver |
| time_ordered | 1,731 | prep_time → rule-based fallback |
| traffic_raw | 601 | Impute mode ('low') in fact_orders |
| city_raw | 1,200 | Impute mode ('Metropolitian') in fact_orders |
| festival_raw | 228 | Impute mode ('no') in fact_orders |
| multiple_deliveries | 993 | Impute mode (1) in fact_orders |
| weather_raw (NaN) | 616 | Impute mode ('sunny') in fact_orders |
| coordinates = 0 | 3,640 | Flagged → excluded by is_corrupted_coords |

## Run Order

```bash
dbt run --models staging.stg_orders
dbt run --models core.dim_driver core.dim_restaurant
dbt run --models core.fact_orders
dbt run --models marts.fct_orders marts.ml_training_dataset
dbt test
```

Or simply:
```bash
dbt run && dbt test
```

## Expected Row Counts

| Model | Expected Rows |
|---|---|
| stg_orders | 45,593 |
| fact_orders (core) | ~45,593 (with flags) |
| fct_orders (marts) | ~38,000–40,000 (after filtering invalid) |
| ml_training_dataset | ~38,000–40,000 |

## Feature Contract Alignment

The 17 features in ml_training_dataset match feature_contract.py exactly:

Numerical (12): distance_km, log_distance, rider_rating, weather_encoded,
                is_rainy, hour_of_day, day_of_week, is_holiday, order_items,
                pickup_to_hub_km, is_long_distance, is_ramadan

Categorical (5): traffic_level, weather, restaurant_type, city, distance_category

Target: delivery_time_min
