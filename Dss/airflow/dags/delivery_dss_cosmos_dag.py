"""
delivery_dss_cosmos_dag.py
Food Delivery DSS - dbt + ML Pipeline with Cosmos
DAG ID: delivery_dss_pipeline
Schedule: Daily at 2:00 AM
"""

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable
from airflow.exceptions import AirflowException

from cosmos import (
    DbtTaskGroup,
    ProjectConfig,
    ProfileConfig,
    ExecutionConfig,
    RenderConfig,
)
from cosmos.profiles import PostgresUserPasswordProfileMapping

logger = logging.getLogger(__name__)

BASE_PATH   = Variable.get("BASE_PATH",        default_var="/mnt/d/Food Delivery Dss")
VENV_PYTHON = Variable.get("VENV_PYTHON",      default_var="/mnt/d/Food Delivery Dss/venv/bin/python3")
DBT_PATH    = Variable.get("DBT_PROJECT_PATH", default_var="/mnt/d/Food Delivery Dss/delivery_transform")

profile_config = ProfileConfig(
    profile_name="delivery_transform",
    target_name="dev",
    profile_mapping=PostgresUserPasswordProfileMapping(
        conn_id="postgres_delivery",
        profile_args={"schema": "public"},
    ),
)

execution_config = ExecutionConfig(
    dbt_executable_path=f"{BASE_PATH}/venv/bin/dbt",
)

project_config = ProjectConfig(
    dbt_project_path=DBT_PATH,
)

default_args = {
    "owner":             "delivery_dss",
    "depends_on_past":   False,
    "retries":           2,
    "retry_delay":       timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}

with DAG(
    dag_id="delivery_dss_pipeline",
    default_args=default_args,
    description=(
        "Food Delivery DSS Pipeline. "
        "Clean pipeline → baseline model (production). "
        "New ML pipeline → experimental model (higher coverage). "
        "Switch via MODEL_VARIANT=new_ml environment variable."
    ),
    schedule_interval="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["delivery", "dss", "dbt", "cosmos", "ml"],
    max_active_runs=1,
) as dag:

    dbt_clean_pipeline = DbtTaskGroup(
        group_id="dbt_clean_pipeline",
        project_config=project_config,
        profile_config=profile_config,
        execution_config=execution_config,
        render_config=RenderConfig(
            select=["stg_orders", "dim_driver", "dim_restaurant",
                    "fact_orders", "fct_orders", "ml_training_dataset"],
        ),
        operator_args={"install_deps": True},
        default_args={"retries": 2},
    )

    dbt_new_ml_pipeline = DbtTaskGroup(
        group_id="dbt_new_ml_pipeline",
        project_config=project_config,
        profile_config=profile_config,
        execution_config=execution_config,
        render_config=RenderConfig(
            select=["fct_orders_new_ml"],
        ),
        operator_args={"install_deps": True},
        default_args={"retries": 2},
    )

    @task(task_id="train_new_ml_model")
    def train_new_ml_model():
        import subprocess, joblib, os
        base   = Variable.get("BASE_PATH", default_var="/mnt/d/Food Delivery Dss")
        python = Variable.get("VENV_PYTHON", default_var=f"{base}/venv/bin/python3")
        logger.info("Training new ML model (experimental)...")
        result = subprocess.run(
            [python, "ml_models_new_ml.py"],
            cwd=base, capture_output=True, text=True, check=True,
        )
        logger.info(result.stdout)
        meta_path = os.path.join(base, "models", "feature_metadata_new_ml.joblib")
        if os.path.exists(meta_path):
            meta = joblib.load(meta_path)
            metrics = meta.get("metrics", {})
            return {"status": "success",
                    "r2": float(metrics.get("r2", 0)),
                    "mae": float(metrics.get("mae", 0))}
        return {"status": "success", "r2": 0.0, "mae": 0.0}

    @task(task_id="train_baseline_model")
    def train_baseline_model():
        import subprocess, joblib, os
        base   = Variable.get("BASE_PATH", default_var="/mnt/d/Food Delivery Dss")
        python = Variable.get("VENV_PYTHON", default_var=f"{base}/venv/bin/python3")
        logger.info("Training baseline model (production)...")
        result = subprocess.run(
            [python, "ml_models_enhanced.py"],
            cwd=base, capture_output=True, text=True, check=True,
        )
        logger.info(result.stdout)
        meta_path = os.path.join(base, "models", "feature_metadata.joblib")
        if os.path.exists(meta_path):
            meta = joblib.load(meta_path)
            metrics = meta.get("metrics", {})
            return {"status": "success",
                    "r2": float(metrics.get("r2", 0)),
                    "mae": float(metrics.get("mae", 0))}
        return {"status": "success", "r2": 0.0, "mae": 0.0}

    @task(task_id="validate_pipeline")
    def validate_pipeline():
        import os
        from sqlalchemy import create_engine, text
        base   = Variable.get("BASE_PATH", default_var="/mnt/d/Food Delivery Dss")
        checks = {}
        errors = []
        model_files = {
            "model_baseline": "models/eta_pipeline.joblib",
            "model_new_ml":   "models/eta_pipeline_new_ml.joblib",
            "contract":       "models/feature_contract.joblib",
        }
        for key, path in model_files.items():
            exists = os.path.exists(os.path.join(base, path))
            checks[key] = exists
            if not exists:
                errors.append(f"Missing file: {path}")
        engine = create_engine("postgresql://root:root@localhost:5555/food_delivery")
        table_queries = {
            "fct_orders_rows": "SELECT COUNT(*) FROM dbt_schema_marts.fct_orders",
            "ml_dataset_rows": "SELECT COUNT(*) FROM dbt_schema_marts.ml_training_dataset",
            "new_ml_rows":     "SELECT COUNT(*) FROM dbt_schema_marts.fct_orders_new_ml",
        }
        with engine.connect() as conn:
            for key, query in table_queries.items():
                try:
                    count = conn.execute(text(query)).scalar()
                    checks[key] = count
                    if count == 0:
                        errors.append(f"Empty table: {key}")
                except Exception as exc:
                    errors.append(f"Query failed for {key}: {exc}")
                    checks[key] = -1
        if errors:
            raise AirflowException("Validation failed:\n" + "\n".join(errors))
        logger.info(f"All validation checks passed: {checks}")
        return {"status": "success", "checks": checks}

    @task(task_id="pipeline_summary")
    def pipeline_summary(new_ml_metrics, baseline_metrics, validation):
        checks = validation.get("checks", {})
        print("══════════════════════════════════════════")
        print("   DELIVERY DSS PIPELINE COMPLETE")
        print("══════════════════════════════════════════")
        print(f"🧹 Clean dbt pipeline:")
        print(f"   fct_orders:          {checks.get('fct_orders_rows', '?')} rows")
        print(f"   ml_training_dataset: {checks.get('ml_dataset_rows', '?')} rows")
        print(f"🔬 New ML dbt pipeline:")
        print(f"   fct_orders_new_ml:   {checks.get('new_ml_rows', '?')} rows")
        print(f"🤖 Baseline model (PRODUCTION):")
        print(f"   R²:  {baseline_metrics.get('r2', 0):.4f}")
        print(f"   MAE: {baseline_metrics.get('mae', 0):.2f} min")
        print(f"🔬 New ML model (experimental — higher coverage):")
        print(f"   R²:  {new_ml_metrics.get('r2', 0):.4f}")
        print(f"   MAE: {new_ml_metrics.get('mae', 0):.2f} min")
        print(f"✅ Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("══════════════════════════════════════════")
        return {"status": "success", "timestamp": datetime.now().isoformat()}

    new_ml   = train_new_ml_model()
    baseline = train_baseline_model()
    valid    = validate_pipeline()
    summary  = pipeline_summary(new_ml, baseline, valid)

    dbt_clean_pipeline  >> baseline
    dbt_new_ml_pipeline >> new_ml
    [new_ml, baseline]  >> valid >> summary