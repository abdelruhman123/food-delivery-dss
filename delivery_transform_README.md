# delivery_transform — dbt Project

## Overview

dbt project for the Food Delivery DSS.
Transforms raw Kaggle delivery data into clean analytical and ML-ready datasets.

**dbt version:** 1.8.7
**Adapter:** postgres 1.9.1
**Tests:** 12/12 passing

---

## Layer Architecture

```
public.raw_deliveries (45,593 rows — loaded via ingest_data.py)
        │
        ▼
STAGING
  stg_orders (view)
  • Rename all columns to snake_case
  • Cast types (string → integer, float, date, time)
  • Handle string 'NaN' literals → real NULL
  • Strip "conditions " prefix from weather
  • Extract integer from "(min) 24" → 24
        │
        ▼
CORE
  dim_driver (table, 1,320 rows)
  • One row per driver
  • Impute driver_age nulls → median
  • Impute rider_rating nulls → median

  dim_restaurant (table, 4 rows)
  • Map order_type → restaurant_type
    Snack/Drinks/Buffet → fast_food
    Meal → casual
  • Map city → area_density

  fact_orders (table, 45,593 rows)
  • Join stg_orders + dim_driver + dim_restaurant
  • Engineer prep_time_min from timestamps (midnight rollover handled)
  • Calculate Haversine distance_km
  • Calculate avg_speed_kmh
  • Apply 3-layer quality flags:
      Layer 1: is_corrupted_coords (lat=0 or lon=0)
      Layer 2: is_invalid_time (<=0 or >240 min)
      Layer 3: is_impossible_speed (>120 km/h)
        │
        ▼
MARTS (CLEAN PIPELINE)
  fct_orders (table, 41,507 rows)
  • Only valid rows (is_valid_row = true)
  • 24 engineered features
  • Source for dashboards + analytics

  ml_training_dataset (view, 40,182 rows)
  • 17 numerical + 7 categorical features
  • Target: delivery_time_min
  • Source for ml_models_enhanced.py

MARTS (EXPERIMENTAL PIPELINE)
  fct_orders_new_ml (table, 45,593 rows)
  • Minimal filtering (keeps all rows)
  • Timestamp-based features
  • Source for ml_models_new_ml.py
```

---

## Models Summary

| Model | Layer | Type | Rows | Purpose |
|---|---|---|---|---|
| stg_orders | staging | view | 45,593 | Clean + rename raw data |
| dim_driver | core | table | 1,320 | Driver profiles |
| dim_restaurant | core | table | 4 | Restaurant type mappings |
| fact_orders | core | table | 45,593 | Joined fact with quality flags |
| fct_orders | marts | table | 41,507 | Clean analytics dataset |
| ml_training_dataset | marts | view | 40,182 | Production ML training |
| fct_orders_new_ml | marts | table | 45,593 | Experimental ML training |

---

## Feature Contract (ml_training_dataset)

### Numerical Features (17)
```
distance_km, log_distance, rider_rating, weather_encoded,
is_rainy, hour_of_day, day_of_week, is_holiday, is_weekend,
order_items, pickup_to_hub_km, is_long_distance, is_ramadan,
driver_age, vehicle_condition, order_month, order_prepare_time
```

### Categorical Features (7)
```
traffic_level, weather, restaurant_type, city,
distance_category, vehicle_type, order_time_period
```

### Target
```
delivery_time_min
```

---

## Null Handling

| Column | Nulls | Strategy |
|---|---|---|
| driver_age | 1,854 | Median imputation in dim_driver |
| rider_rating | 1,908 | Median imputation in dim_driver |
| time_ordered | 1,731 | prep_time → rule-based fallback |
| traffic_raw | 601 | Mode imputation ('low') in fact_orders |
| city_raw | 1,200 | Mode imputation ('Metropolitian') |
| festival_raw | 228 | Mode imputation ('no') |
| multiple_deliveries | 993 | Mode imputation (1) |
| weather_raw | 616 | Mode imputation ('sunny') |
| coordinates = 0 | 3,640 | Flagged → excluded by quality filter |

---

## Running the Pipeline

```bash
cd delivery_transform

# Run all models
dbt run

# Run tests
dbt test

# Run specific pipeline
dbt run --select stg_orders dim_driver dim_restaurant fact_orders fct_orders ml_training_dataset

# Run experimental pipeline
dbt run --select fct_orders_new_ml
```

---

## dbt Tests (12/12 passing)

- `source_not_null_public_raw_deliveries_*` (4 tests)
- `source_unique_public_raw_deliveries_id` (1 test)
- `not_null` tests on key columns (7 tests)

---

## Connection

```yaml
# profiles.yml
delivery_transform:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5555
      user: root
      password: root
      dbname: food_delivery
      schema: public
```

---

## Schema Outputs

```
dbt_schema_staging.stg_orders
dbt_schema_core.dim_driver
dbt_schema_core.dim_restaurant
dbt_schema_core.fact_orders
dbt_schema_marts.fct_orders
dbt_schema_marts.ml_training_dataset
dbt_schema_marts.fct_orders_new_ml
```
