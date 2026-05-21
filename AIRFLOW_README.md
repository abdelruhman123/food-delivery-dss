# Airflow README — Food Delivery DSS

Orchestrates the complete data and ML pipeline using Apache Airflow 2.10.5
with Astronomer Cosmos for dbt integration.

## DAG — `delivery_dss_pipeline`

Single DAG with two parallel pipelines running daily at 2:00 AM.

### Phase 1A — Clean dbt Pipeline (Cosmos TaskGroup)
Runs these dbt models in dependency order:
- `stg_orders` → staging view
- `dim_driver`, `dim_restaurant` → core dimension tables
- `fact_orders` → core fact table with 3-layer quality flags
- `fct_orders` → marts table (41,507 clean rows)
- `ml_training_dataset` → marts view (40,182 rows, 24 features)

Used for: dashboards, KPIs, analytics, production ML training.

### Phase 1B — New ML dbt Pipeline (Cosmos TaskGroup)
Runs in parallel with Phase 1A:
- `fct_orders_new_ml` → experimental dataset (45,593 rows, minimal filtering)

Used for: experimental ML training only.

### Phase 2A — Train Baseline Model
Triggered after Phase 1A completes:
- Runs `ml_models_enhanced.py`
- Trains RandomForest on `ml_training_dataset`
- R² = 0.61 (production model, clean data)
- Saves `models/eta_pipeline.joblib`

### Phase 2B — Train New ML Model
Triggered after Phase 1B completes:
- Runs `ml_models_new_ml.py`
- Trains RandomForest on `fct_orders_new_ml`
- R² = 0.73 (experimental model, higher coverage)
- Saves `models/eta_pipeline_new_ml.joblib`

### Phase 3 — Validate Pipeline
Triggered after both training tasks complete:
- Checks all model files exist
- Verifies row counts in all dbt tables
- Raises AirflowException if any check fails

### Phase 4 — Pipeline Summary
Prints final summary with metrics for both models.

## Task Dependencies

```
dbt_clean_pipeline  ──► train_baseline_model ──┐
                                                ├──► validate_pipeline ──► pipeline_summary
dbt_new_ml_pipeline ──► train_new_ml_model  ───┘
```

## ML Artifacts

### Production (baseline):
- `models/eta_pipeline.joblib`
- `models/scaler.joblib`
- `models/feature_contract.joblib`
- `models/feature_metadata.joblib`

### Experimental (new_ml):
- `models/eta_pipeline_new_ml.joblib`
- `models/label_encoders_new_ml.joblib`
- `models/feature_metadata_new_ml.joblib`

## Model Selection

The production API uses the baseline model by default.
Switch to the experimental model via environment variable:

```bash
# Production (default)
uvicorn eta_api:app --port 8000

# Experimental
MODEL_VARIANT=new_ml uvicorn eta_api:app --port 8000
```

## Setup

### Airflow Variables Required
```
BASE_PATH         = /mnt/d/Food Delivery Dss
VENV_PYTHON       = /mnt/d/Food Delivery Dss/venv/bin/python3
DBT_PROJECT_PATH  = /mnt/d/Food Delivery Dss/delivery_transform
```

### Airflow Connection Required
```
Connection ID:   postgres_delivery
Type:            Postgres
Host:            localhost
Port:            5555
Schema:          food_delivery
Login:           root
Password:        root
```

## Running Airflow

```bash
# Terminal 1 — Webserver
source venv/bin/activate
airflow webserver --port 8080

# Terminal 2 — Scheduler
source venv/bin/activate
airflow scheduler
```

Open UI at: http://localhost:8080
Login: admin / admin123
