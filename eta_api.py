"""
eta_api.py  —  Food Delivery ETA Inference API  v4.0.0
=======================================================
Run: uvicorn eta_api:app --reload --port 8000
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

# ── Model variant switch (set MODEL_VARIANT=new_ml to test) ──────────────────
MODEL_VARIANT = os.getenv("MODEL_VARIANT", "production")

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sklearn.preprocessing import LabelEncoder
from sqlalchemy import create_engine, text

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_DSS  = os.path.join(_HERE, "Dss")
if _DSS  not in sys.path: sys.path.insert(0, _DSS)
if _HERE not in sys.path: sys.path.insert(0, _HERE)

from db_manager import DatabaseManager
from feature_contract import (
    get_numerical_features, get_categorical_features,
    get_all_features, get_distance_category,
    get_weather_encoded, get_is_rainy, get_target,
)
from backend_logic import calculate_prep_time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eta_api")

DB_URL = "postgresql://root:root@localhost:5555/food_delivery"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_time_period(hour: int) -> str:
    if hour in range(0, 6):   return "night"
    if hour in range(6, 12):  return "morning"
    if hour in range(12, 15): return "noon"
    if hour in range(15, 20): return "afternoon"
    return "evening"


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if MODEL_VARIANT == "new_ml":
        app.state.pipeline       = joblib.load("models/eta_pipeline_new_ml.joblib")
        app.state.scaler         = None  # new_ml model was trained with its own scaler inside joblib
        app.state.meta           = joblib.load("models/feature_metadata_new_ml.joblib")
        app.state.label_encoders = joblib.load("models/label_encoders_new_ml.joblib")
        logger.info("✓ New ML model + label encoders loaded.")
    else:
        app.state.pipeline = joblib.load("models/eta_pipeline.joblib")
        app.state.scaler   = joblib.load("models/scaler.joblib")
        app.state.meta     = None
        logger.info("✓ Production model loaded (MODEL_VARIANT=production).")
    app.state.db = DatabaseManager()
    logger.info("✓ DB connected.")
    yield
    logger.info("ETA API shutdown.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Food Delivery ETA Inference API",
    version="4.0.0",
    lifespan=lifespan,
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ETARequest(BaseModel):
    order_id:            str
    origin_lat:          float
    origin_lng:          float
    dest_lat:            float
    dest_lng:            float
    distance_km:         float = Field(..., gt=0, description="Road distance from Google Maps (km)")
    google_duration_min: float = Field(..., gt=0, description="Travel time from Google Maps (minutes)")
    restaurant_type:     Literal["fast_food", "casual", "fine_dine", "cafe"]
    order_items:         int   = Field(..., ge=1, le=50)
    traffic_level:       Literal["low", "medium", "high"]
    weather:             Literal["clear", "cloudy", "rainy", "stormy"] = "clear"
    rider_rating:        float = Field(default=4.5, ge=0, le=5)
    vehicle_type:        str   = "motorcycle"
    city:                str   = "Metropolitian"
    driver_age:          int   = 29


class ETAResponse(BaseModel):
    order_id:          str
    prep_time_min:     float
    delivery_time_min: float   # ML correction value (for backward compatibility)
    total_eta_min:     float
    distance_km:       float
    distance_category: str
    # Hybrid ETA debug fields
    base_eta:          float
    google_travel_time: float
    ml_eta_raw:        float
    ml_adjustment:     float
    model_variant:     str     # "production" or "new_ml"


class KitchenStatusRequest(BaseModel):
    order_id: str
    status:   Literal["Preparing", "Ready", "Delivered"]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health() -> dict:
    loaded = hasattr(app.state, "pipeline") and app.state.pipeline is not None
    return {
        "status":          "ok" if loaded else "degraded",
        "pipeline_loaded": loaded,
        "timestamp":       datetime.now().isoformat(),
    }


@app.get("/schema", tags=["ops"])
def schema() -> dict:
    return {
        "features":       get_all_features(),
        "target":         get_target(),
        "total_features": len(get_all_features()),
        "version":        "4.0.0",
    }


@app.post("/predict-eta", response_model=ETAResponse, tags=["inference"])
def predict_eta(request: ETARequest) -> ETAResponse:
    # 1. Distance — use real Google Maps road distance (no Haversine)
    distance_km = request.distance_km

    # 2. Prep time — use Chef's confirmed value from DB if available
    #    Fall back to backend_logic only if not confirmed yet
    prep_time = None
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=5555, database="food_delivery",
            user="root", password="root"
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT confirmed_prep_time FROM orders WHERE order_id = %s",
                (request.order_id,)
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                prep_time = float(row[0])
                logger.info(
                    "Using chef confirmed prep_time=%.1f for order %s",
                    prep_time, request.order_id
                )
        conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch confirmed_prep_time: {e}")

    if prep_time is None:
        try:
            prep_time, _, _ = calculate_prep_time(
                restaurant_type=request.restaurant_type,
                order_items=[[f"item_{i}", 1] for i in range(request.order_items)],
                station_workload={},
            )
        except Exception:
            prep_time = 10.0

    # 3. Time features
    now = datetime.now()

    # 4. Feature row — exact same 24 features as training
    feature_row = {
        "distance_km":       distance_km,
        "log_distance":      float(np.log(1 + distance_km)),
        "rider_rating":      request.rider_rating,
        "weather_encoded":   get_weather_encoded(request.weather),
        "is_rainy":          get_is_rainy(request.weather),
        "hour_of_day":       float(now.hour),
        "day_of_week":       float(now.weekday()),
        "is_holiday":        1.0 if now.weekday() in (4, 5) else 0.0,
        "is_weekend":        1.0 if now.weekday() in (5, 6) else 0.0,
        "order_items":       float(request.order_items),
        "pickup_to_hub_km":  (2.5 if request.city == "Metropolitian"
                              else 1.8 if request.city == "Urban"
                              else 1.2),
        "is_long_distance":  1.0 if distance_km > 20 else 0.0,
        "is_ramadan":        0.0,
        "driver_age":        float(request.driver_age),
        "vehicle_condition": 1.0,
        "order_month":       float(now.month),
        "order_prepare_time": prep_time,
        "pickup_delay_min":  prep_time,
        "traffic_level":     request.traffic_level,
        "weather":           request.weather,
        "restaurant_type":   request.restaurant_type,
        "city":              request.city,
        "distance_category": get_distance_category(distance_km),
        "vehicle_type":      request.vehicle_type,
        "order_time_period": get_time_period(now.hour),
    }

    # 5. LabelEncode categoricals
    cat_cols = get_categorical_features()
    df = pd.DataFrame([feature_row])
    # Production model uses scaler — fix single-row fitting with known categories
    _known_cats = {
        "traffic_level":    ["low", "medium", "high"],
        "weather":          ["clear", "cloudy", "rainy", "stormy"],
        "restaurant_type":  ["fast_food", "casual", "fine_dine", "cafe"],
        "city":             ["Metropolitian", "Urban", "Semi-Urban"],
        "distance_category":["local", "city", "long_range", "extreme"],
        "vehicle_type":     ["motorcycle", "scooter", "electric_scooter", "bicycle"],
        "order_time_period":["night", "morning", "noon", "afternoon", "evening"],
    }
    for col in cat_cols:
        le = LabelEncoder()
        known = _known_cats.get(col, [str(df[col].iloc[0])])
        le.fit([str(v) for v in known])
        val = str(df[col].iloc[0])
        df[col] = le.transform([val]) if val in le.classes_ else [0]

    # 6. Scale and build input
    if MODEL_VARIANT == "new_ml":
        # New ML model: use feature list from saved metadata, fill missing with defaults
        new_ml_features = app.state.meta.get("features", list(feature_row.keys()))
        kaggle_defaults = {
            "min_order":          float(now.minute),
            "hour_order_picked":  float(now.hour),
            "min_order_picked":   float(now.minute),
            "pickup_delay_min":   prep_time,
            "order_day":          float(now.day),
        }
        for feat in new_ml_features:
            if feat not in feature_row:
                feature_row[feat] = kaggle_defaults.get(feat, 0.0)
        # Map real city names to training categories
        _CITY_MAP = {
            "Cairo":       "Metropolitian",
            "Giza":        "Metropolitian",
            "Alexandria":  "Urban",
            "Mansoura":    "Urban",
            "Tanta":       "Urban",
            "Assiut":      "Semi-Urban",
            "Zagazig":     "Semi-Urban",
        }
        if "city" in feature_row:
            feature_row["city"] = _CITY_MAP.get(feature_row["city"], "Metropolitian")
        df_k = pd.DataFrame([feature_row])
        # Use saved label encoders — fixes single-row fitting bug
        label_encoders = app.state.label_encoders
        for col in new_ml_features:
            if col in label_encoders and df_k[col].dtype == object:
                le  = label_encoders[col]
                val = str(df_k[col].iloc[0])
                df_k[col] = le.transform([val]) if val in le.classes_ else [0]
        X = df_k[new_ml_features].astype(float)
        X_scaled = X.values
    else:
        num_cols = get_numerical_features()
        X        = df[num_cols + cat_cols]
        X_scaled = app.state.scaler.transform(X)

    # 7. ML corrects Google travel time; confirmed prep added on top
    ml_raw = float(app.state.pipeline.predict(X_scaled)[0])
    # Blend: 60% Google (real road) + 40% ML (traffic patterns)
    travel_time   = (0.6 * request.google_duration_min) + (0.4 * ml_raw)
    # Add real confirmed prep time on top
    total_eta     = travel_time + prep_time
    # Debug fields
    base_eta      = request.google_duration_min + prep_time
    ml_adjustment = travel_time - request.google_duration_min
    ml_eta        = ml_raw

    logger.info(
        "predict-eta | order=%s | dist=%.2f km | google=%.1f min | "
        "prep=%.1f min | base_eta=%.1f | ml_eta=%.1f | adj=%.1f | total=%.1f",
        request.order_id, distance_km, request.google_duration_min,
        prep_time, base_eta, ml_eta, ml_adjustment, total_eta,
    )

    # 8. Save to DB
    app.state.db.update_order_eta(
        order_id=request.order_id,
        ml_travel_prediction=ml_adjustment,
        total_eta=total_eta,
    )

    # 9. Return with full debug breakdown
    return ETAResponse(
        order_id=request.order_id,
        prep_time_min=round(prep_time, 1),
        delivery_time_min=round(travel_time, 1),  # travel time only
        total_eta_min=round(total_eta, 1),         # travel + prep
        distance_km=round(distance_km, 2),
        distance_category=get_distance_category(distance_km),
        base_eta=round(base_eta, 1),
        google_travel_time=round(request.google_duration_min, 1),
        ml_eta_raw=round(ml_eta, 1),
        ml_adjustment=round(ml_adjustment, 1),
        model_variant=MODEL_VARIANT,
    )


@app.post("/kitchen-status", tags=["ops"])
def kitchen_status(request: KitchenStatusRequest) -> dict:
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", port=5555, database="food_delivery",
        user="root", password="root",
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status=%s WHERE order_id=%s",
                (request.status, request.order_id),
            )
    conn.close()
    return {"order_id": request.order_id, "status": request.status, "updated": True}


@app.get("/dashboard-kpis", tags=["ops"])
def dashboard_kpis() -> dict:
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        traffic = conn.execute(text("""
            SELECT traffic_level,
                   round(avg(delivery_time_min)::numeric, 2) AS avg_delivery,
                   count(*) AS total_orders
            FROM dbt_schema_marts.fct_orders
            GROUP BY traffic_level
            ORDER BY avg_delivery
        """)).mappings().all()

        summary = conn.execute(text("""
            SELECT round(avg(delivery_time_min)::numeric, 2) AS overall_avg,
                   round(min(delivery_time_min)::numeric, 2) AS min_time,
                   round(max(delivery_time_min)::numeric, 2) AS max_time,
                   count(*) AS total_orders
            FROM dbt_schema_marts.fct_orders
        """)).mappings().first()

        recent = conn.execute(text("""
            SELECT order_id, restaurant_type, status,
                   ml_travel_prediction, total_eta, created_at
            FROM orders
            ORDER BY created_at DESC
            LIMIT 20
        """)).mappings().all()

    return {
        "traffic_breakdown": [dict(r) for r in traffic],
        "summary":           dict(summary) if summary else {},
        "recent_orders":     [dict(r) for r in recent],
    }
