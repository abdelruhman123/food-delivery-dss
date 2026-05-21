from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sqlalchemy import create_engine
from xgboost import XGBRegressor

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL      = "postgresql://root:root@localhost:5555/food_delivery"
SOURCE_VIEW = "dbt_schema_marts.fct_orders_new_ml"
MODELS_DIR  = Path("models")

# ── Columns to attempt loading (graceful if missing) ─────────────────────────
CORE_FEATURES = [
    "distance_km",
    "rider_rating",
    "driver_age",
    "order_items",
    "vehicle_condition",
    "is_rainy",
    "weather_encoded",
    "hour_of_day",
    "day_of_week",
    "is_holiday",
    "is_weekend",
    "is_long_distance",
    "is_ramadan",
    "order_month",
    "pickup_to_hub_km",
    "log_distance",
    "order_prepare_time",
    "pickup_delay_min",
    # Physics-based (added in v4.1.0)
    "estimated_speed_kmh",
    "estimated_travel_time_min",
    "distance_traffic_score",
    "is_peak_hour",
    "distance_peak_score",
    "kitchen_load_score",
]

KAGGLE_EXTRA_FEATURES = [
    # Timestamp-derived (may introduce leakage)
    "order_day",
    "min_order",
    "hour_order_picked",
    "min_order_picked",
]

CATEGORICAL_FEATURES = [
    "traffic_level",
    "weather",
    "restaurant_type",
    "vehicle_type",
    "city",
    "distance_category",
    "order_time_period",
]

TARGET = "delivery_time_min"


def load_data() -> pd.DataFrame:
    print(f"Loading data from {SOURCE_VIEW} ...")
    engine = create_engine(DB_URL)
    df = pd.read_sql(f"SELECT * FROM {SOURCE_VIEW}", engine)
    print(f"Raw rows loaded: {len(df)}")
    return df


def compute_pickup_delay(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive pickup_delay_min from raw timestamp columns if available.
    Kaggle notebooks often compute: Time_Order_picked - Time_Orderd
    """
    # fct_orders exposes hour_order_picked and min_order, so we approximate:
    if "hour_order_picked" in df.columns and "hour_of_day" in df.columns:
        df["pickup_delay_min"] = (
            (df["hour_order_picked"] - df["hour_of_day"]) * 60
            + df.get("min_order_picked", pd.Series(0, index=df.index))
            - df.get("min_order", pd.Series(0, index=df.index))
        ).clip(lower=0)
        print("  ✓ pickup_delay_min derived from hour/min columns")
    else:
        print("  ⚠ pickup_delay_min skipped — required columns not found")
    return df


def select_features(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return (numerical_features, categorical_features) that actually exist."""
    all_candidates = CORE_FEATURES + KAGGLE_EXTRA_FEATURES
    num_features = [c for c in all_candidates if c in df.columns]
    cat_features = [c for c in CATEGORICAL_FEATURES if c in df.columns]
    return num_features, cat_features


def print_metrics(name: str, y_test, y_pred, n_rows: int, n_features: int) -> dict:
    mae  = float(mean_absolute_error(y_test, y_pred))
    mse  = float(mean_squared_error(y_test, y_pred))
    rmse = float(np.sqrt(mse))
    r2   = float(r2_score(y_test, y_pred))
    print(f"\n{'─'*50}")
    print(f"  {name}")
    print(f"{'─'*50}")
    print(f"  Rows      : {n_rows:,}")
    print(f"  Features  : {n_features}")
    print(f"  MAE       : {mae:.4f} min")
    print(f"  RMSE      : {rmse:.4f} min")
    print(f"  R²        : {r2:.4f}")
    print(f"{'─'*50}")
    return {"mae": mae, "mse": mse, "rmse": rmse, "r2": r2}


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load ──────────────────────────────────────────────────────────────────
    df = load_data()

    # ── Derive pickup_delay_min ───────────────────────────────────────────────
    df = compute_pickup_delay(df)

    # ── Minimal filtering — only drop missing/impossible target rows ──────────
    before = len(df)
    df = df[df[TARGET].notna() & (df[TARGET] > 0)]
    print(f"After minimal filter: {len(df):,} rows (dropped {before - len(df):,})")

    # ── Select features ───────────────────────────────────────────────────────
    num_features, cat_features = select_features(df)
    all_features = num_features + cat_features
    print(f"\nNumerical features ({len(num_features)}): {num_features}")
    print(f"Categorical features ({len(cat_features)}): {cat_features}")
    print(f"Total features: {len(all_features)}")

    # ── Fill missing values ───────────────────────────────────────────────────
    for col in num_features:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(df[col].median())
    for col in cat_features:
        df[col] = df[col].fillna("unknown").astype(str)

    # ── LabelEncode categoricals ──────────────────────────────────────────────
    label_encoders = {}
    for col in cat_features:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        label_encoders[col] = le

    joblib.dump(label_encoders, MODELS_DIR / "label_encoders_new_ml.joblib")
    print("Label encoders saved → models/label_encoders_new_ml.joblib")

    # ── Split ─────────────────────────────────────────────────────────────────
    X = df[all_features]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # ── Scale ─────────────────────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)

    n_rows     = len(df)
    n_features = len(all_features)
    best_model = None
    best_r2    = -np.inf
    best_name  = ""
    all_metrics: dict = {}

    # ── Model 1: RandomForest ─────────────────────────────────────────────────
    print("\nTraining RandomForest (New ML) ...")
    rf = RandomForestRegressor(
        n_estimators=500,
        max_features=10,
        min_samples_split=10,
        min_samples_leaf=1,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train_sc, y_train)
    rf_metrics = print_metrics(
        "RandomForest (New ML)",
        y_test, rf.predict(X_test_sc),
        n_rows, n_features,
    )
    all_metrics["RandomForest"] = rf_metrics
    if rf_metrics["r2"] > best_r2:
        best_r2, best_model, best_name = rf_metrics["r2"], rf, "RandomForest"

    # ── Model 2: XGBoost ──────────────────────────────────────────────────────
    print("\nTraining XGBoost (New ML) ...")
    xgb = XGBRegressor(
        eta=0.1,
        max_depth=7,
        min_child_weight=6,
        subsample=1.0,
        n_estimators=500,
        random_state=42,
        n_jobs=-1,
    )
    xgb.fit(X_train_sc, y_train)
    xgb_metrics = print_metrics(
        "XGBoost (New ML)",
        y_test, xgb.predict(X_test_sc),
        n_rows, n_features,
    )
    all_metrics["XGBoost"] = xgb_metrics
    if xgb_metrics["r2"] > best_r2:
        best_r2, best_model, best_name = xgb_metrics["r2"], xgb, "XGBoost"

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*50}")
    print(f"  Best New ML: {best_name}  (R²={best_r2:.4f})")
    print(f"  Clean DSS baseline:      RandomForest (R²≈0.60)")
    print(f"{'═'*50}")

    # ── Save (separate files — never overwrites production) ───────────────────
    pipeline_path = MODELS_DIR / "eta_pipeline_new_ml.joblib"
    meta_path     = MODELS_DIR / "feature_metadata_new_ml.joblib"

    joblib.dump(best_model, pipeline_path)
    print(f"\nModel saved  → {pipeline_path}")

    metadata = {
        "trained_at":         datetime.now().isoformat(),
        "script":             "ml_models_new_ml.py",
        "source":             SOURCE_VIEW,
        "rows_total":         n_rows,
        "rows_trained":       len(X_train),
        "model_type":         best_name,
        "model_params":       best_model.get_params(),
        "numerical_features": num_features,
        "categorical_features": cat_features,
        "features":           all_features,
        "target":             TARGET,
        "metrics":            all_metrics[best_name],
        "all_model_metrics":  all_metrics,
        "note": (
            "New ML-style model. Target: travel_time_min (pure travel, prep excluded). "
            "pickup_delay_min (confirmed prep time) is a feature. "
            "At inference: total_eta = ml_travel_prediction + confirmed_prep_time."
        ),
    }
    joblib.dump(metadata, meta_path)
    print(f"Metadata saved → {meta_path}")
    print("\nDone. Production model files were NOT modified.")


if __name__ == "__main__":
    main()
