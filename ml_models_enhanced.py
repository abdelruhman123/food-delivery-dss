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

from feature_contract import (
    freeze_contract,
    get_all_features,
    get_categorical_features,
    get_numerical_features,
    get_target,
    validate_training_schema,
)

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL      = "postgresql://root:root@localhost:5555/food_delivery"
SOURCE_VIEW = "dbt_schema_marts.ml_training_dataset"
MODELS_DIR  = Path("models")


def main() -> None:
    # ── Load data ─────────────────────────────────────────────────────────────
    print(f"Loading data from {SOURCE_VIEW}...")
    engine = create_engine(DB_URL)
    df = pd.read_sql(f"SELECT * FROM {SOURCE_VIEW}", engine)
    print(f"Rows loaded: {len(df)}")

    num_f = get_numerical_features()
    cat_f = get_categorical_features()
    print(f"Features: {len(get_all_features())} ({len(num_f)} numerical + {len(cat_f)} categorical)")

    # ── LabelEncode categoricals in-place ────────────────────────────────────
    for col in cat_f:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))

    # ── Validate schema BEFORE split ─────────────────────────────────────────
    # Drop identifier — not a feature
    df = df.drop(columns=['order_id'])
    validate_training_schema(df)
    print("Schema validated ✓")

    # ── Split ─────────────────────────────────────────────────────────────────
    X = df[get_all_features()]
    y = df[get_target()]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # ── Scale ─────────────────────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)

    # ── Train ─────────────────────────────────────────────────────────────────
    print("Training XGBoost...")
    model = XGBRegressor(
        eta=0.1,
        max_depth=7,
        min_child_weight=6,
        subsample=1.0,
        random_state=42,
        n_estimators=500,
    )
    model.fit(X_train_sc, y_train)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    y_pred = model.predict(X_test_sc)

    MAE  = float(mean_absolute_error(y_test, y_pred))
    MSE  = float(mean_squared_error(y_test, y_pred))
    RMSE = float(np.sqrt(MSE))
    R2   = float(r2_score(y_test, y_pred))

    print("─────────────────────────────")
    print(f"MAE  : {MAE:.2f} min")
    print(f"MSE  : {MSE:.2f}")
    print(f"RMSE : {RMSE:.2f} min")
    print(f"R2   : {R2:.2f}")
    print("─────────────────────────────")

    # ── RandomForest comparison ───────────────────────────────────────────────
    print("Training RandomForest...")
    rf = RandomForestRegressor(
        n_estimators=500,
        max_features=10,
        min_samples_split=10,
        min_samples_leaf=1,
        random_state=42,
    )
    rf.fit(X_train_sc, y_train)
    y_pred_rf = rf.predict(X_test_sc)

    MAE_rf  = float(mean_absolute_error(y_test, y_pred_rf))
    MSE_rf  = float(mean_squared_error(y_test, y_pred_rf))
    RMSE_rf = float(np.sqrt(MSE_rf))
    R2_rf   = float(r2_score(y_test, y_pred_rf))

    print("RandomForest ────────────────")
    print(f"MAE  : {MAE_rf:.2f} min")
    print(f"MSE  : {MSE_rf:.2f}")
    print(f"RMSE : {RMSE_rf:.2f} min")
    print(f"R2   : {R2_rf:.2f}")
    print("─────────────────────────────")

    # ── Select best model ─────────────────────────────────────────────────────
    if R2_rf > R2:
        best_model  = rf
        best_name   = "RandomForest"
        best_metrics = {"mae": MAE_rf, "mse": MSE_rf, "rmse": RMSE_rf, "r2": R2_rf}
    else:
        best_model  = model
        best_name   = "XGBoost"
        best_metrics = {"mae": MAE, "mse": MSE, "rmse": RMSE, "r2": R2}

    print(f"Best model: {best_name} (R2={best_metrics['r2']:.2f})")

    # ── Save artifacts ────────────────────────────────────────────────────────
    os.makedirs(MODELS_DIR, exist_ok=True)

    freeze_contract(MODELS_DIR / "feature_contract.joblib")
    print(f"Contract frozen  → {MODELS_DIR}/feature_contract.joblib")

    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")
    print(f"Scaler saved     → {MODELS_DIR}/scaler.joblib")

    joblib.dump(best_model, MODELS_DIR / "eta_pipeline.joblib")
    print(f"Model saved      → {MODELS_DIR}/eta_pipeline.joblib  ({best_name})")

    metadata = {
        "trained_at":    datetime.now().isoformat(),
        "rows_trained":  int(len(X_train)),
        "model_type":    best_name,
        "model_params":  best_model.get_params(),
        "metrics":       best_metrics,
        "xgboost_metrics": {"mae": MAE, "mse": MSE, "rmse": RMSE, "r2": R2},
        "rf_metrics":      {"mae": MAE_rf, "mse": MSE_rf, "rmse": RMSE_rf, "r2": R2_rf},
        "features":      get_all_features(),
        "target":        get_target(),
        "version":       "4.0.0",
        "preprocessing": "LabelEncoder + StandardScaler",
    }
    joblib.dump(metadata, MODELS_DIR / "feature_metadata.joblib")
    print(f"Metadata saved   → {MODELS_DIR}/feature_metadata.joblib")

    print("Training complete ✓")


if __name__ == "__main__":
    main()
