# Airflow README (Current Project)

This document describes the intended Airflow orchestration for the **Food Delivery DSS**.

## DAGs

### DAG 1 — `dbt_pipeline`

Runs daily:

1. `ingest_data.py` → loads `deliveries.csv` into PostgreSQL (`public.raw_deliveries`)
2. `dbt run` → builds staging → core → marts
3. `dbt test` → validates the 12 dbt tests

### DAG 2 — `ml_training`

Triggered after `dbt_pipeline` succeeds:

1. generate / validate contract (`feature_contract.py`)
2. train model (`ml_models_enhanced.py`)
3. freeze contract → save artifacts into `models/`

## ML artifacts (after training)

- `models/eta_pipeline.joblib`
- `models/feature_contract.joblib`
- `models/feature_metadata.joblib`

## Notes

FastAPI and Streamlit deployment are **not** part of this phase yet. Those come later.
