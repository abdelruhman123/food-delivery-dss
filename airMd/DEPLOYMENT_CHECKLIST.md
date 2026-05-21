# Deployment Checklist (Current Project)

This checklist reflects the current phase: **Docker + dbt + Airflow + ML training artifacts**.

## Infrastructure

- ✅ Docker: `pg_delivery` (PostgreSQL on port 5555)
- ✅ dbt: local project `delivery_transform`
- ✅ Airflow: local
- ⏳ FastAPI: pending
- ⏳ Streamlit: pending

## dbt state

- ✅ `stg_orders` (staging view)
- ✅ `dim_driver`, `dim_restaurant`, `fact_orders` (core tables)
- ✅ `fct_orders` (marts table)
- ✅ `ml_training_dataset` (marts view)
- ✅ 12 dbt tests passing

## ML artifacts (after training)

- ✅ `models/eta_pipeline.joblib`
- ✅ `models/feature_contract.joblib`
- ✅ `models/feature_metadata.joblib`
