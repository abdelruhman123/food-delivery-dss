# DAG Workflow — Food Delivery DSS

End-to-end workflow from raw data to ML artifacts and live predictions.

## Full Pipeline Flow

```
public.raw_deliveries (loaded manually via ingest_data.py)
        │
        ├──────────────────────────────────────────────┐
        │                                              │
        ▼                                              ▼
CLEAN DBT PIPELINE                          NEW ML DBT PIPELINE
stg_orders (staging view)                  stg_orders (same source)
        │                                              │
        ▼                                              ▼
dim_driver, dim_restaurant              fct_orders_new_ml
        │                               (45,593 rows, minimal filter)
        ▼                                              │
fact_orders (core, 45,593 rows)                        ▼
3-layer quality validation              ml_models_new_ml.py
        │                               → eta_pipeline_new_ml.joblib
        ▼                               R² = 0.73 (experimental)
fct_orders (marts, 41,507 rows)
        │
        ▼
ml_training_dataset (view, 40,182 rows)
        │
        ▼
ml_models_enhanced.py
→ eta_pipeline.joblib
R² = 0.61 (production)
```

## dbt Models

### Staging Layer
| Model | Type | Rows | Purpose |
|---|---|---|---|
| stg_orders | view | 45,593 | Rename, cast, clean NaN strings |

### Core Layer
| Model | Type | Rows | Purpose |
|---|---|---|---|
| dim_driver | table | 1,320 | One row per driver, nulls imputed |
| dim_restaurant | table | 4 | Restaurant type mappings |
| fact_orders | table | 45,593 | Joins + quality flags |

### Marts Layer
| Model | Type | Rows | Purpose |
|---|---|---|---|
| fct_orders | table | 41,507 | Clean rows, 24 features, analytics |
| ml_training_dataset | view | 40,182 | Production ML training source |
| fct_orders_new_ml | table | 45,593 | Experimental ML training source |

## ML Models Comparison

| Model | Source | Rows | R² | MAE | Usage |
|---|---|---|---|---|---|
| eta_pipeline.joblib | ml_training_dataset | 40,182 | 0.61 | 4.65 min | Production |
| eta_pipeline_new_ml.joblib | fct_orders_new_ml | 45,593 | 0.73 | 3.83 min | Experimental |

## ETA Prediction Flow (at inference)

```
Manager clicks "Predict Delivery ETA"
        │
        ▼
Google Maps Directions API
→ distance_km (real road distance)
→ google_duration_min (real-time traffic)
→ traffic_level (low/medium/high)
        │
        ▼
POST /predict-eta (FastAPI)
→ fetch confirmed_prep_time from DB (chef's value)
→ build 24 feature vector
→ model.predict() → ml_raw
→ travel_time = 0.6×google + 0.4×ml_raw
→ total_eta = travel_time + confirmed_prep_time
        │
        ▼
Result stored in orders.total_eta
Customer app polls every 10s and displays ETA
```

## Data Quality — 3 Layers

```
Layer 1: is_corrupted_coords
  → lat=0 or lon=0 → 3,640 rows removed

Layer 2: is_invalid_time
  → delivery_time <= 0 or > 240 min → removed

Layer 3: is_impossible_speed
  → avg_speed > 120 km/h → removed

Result: 41,507 clean rows (91% of raw data)
```

## Retry Logic

```
Each task:
  retries:           2
  retry_delay:       5 minutes
  execution_timeout: 2 hours

Failure behavior:
  dbt fails    → ML training does not run
  ML fails     → Previous model stays active
  Validate fails → AirflowException raised, email alert sent
```

## Schedule

```
Daily at 2:00 AM (UTC)
Estimated duration: 10-15 minutes
Bottleneck: ML training (~5-8 min each)
```
