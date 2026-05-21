from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import joblib


FEATURE_CONTRACT: Dict[str, Any] = {
    "numerical_features": [
        "distance_km",
        "log_distance",
        "rider_rating",
        "weather_encoded",
        "is_rainy",
        "hour_of_day",
        "day_of_week",
        "is_holiday",
        "is_weekend",
        "order_items",
        "pickup_to_hub_km",
        "is_long_distance",
        "is_ramadan",
        "driver_age",
        "vehicle_condition",
        "order_month",
        "order_prepare_time",
    ],
    "categorical_features": [
        "traffic_level",
        "weather",
        "restaurant_type",
        "city",
        "distance_category",
        "vehicle_type",
        "order_time_period",
    ],
    "target": "delivery_time_min",
    "excluded_features": [
        "prep_time_min",
        "avg_speed_kmh",
        "order_id",
        "driver_id",
        "city_code",
    ],
    "version": "4.0.0",
    "description": "24-feature schema — order_prepare_time restored (min=5,max=15,avg=9.98), order_time_period added, city_code removed",
}


def get_numerical_features() -> List[str]:
    return list(FEATURE_CONTRACT["numerical_features"])


def get_categorical_features() -> List[str]:
    return list(FEATURE_CONTRACT["categorical_features"])


def get_all_features() -> List[str]:
    return get_numerical_features() + get_categorical_features()


def get_target() -> str:
    return str(FEATURE_CONTRACT["target"])


def _as_set(seq: Sequence[str]) -> set[str]:
    return set(map(str, seq))


def _expected_training_columns() -> List[str]:
    return get_all_features() + [get_target()]


def validate_training_schema(df) -> None:
    """
    Ensures training data contains exactly (features + target) and has no nulls
    in any required column.
    """
    expected = _expected_training_columns()
    actual = list(map(str, getattr(df, "columns", [])))

    expected_set = _as_set(expected)
    actual_set = _as_set(actual)

    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)

    if missing or extra:
        raise ValueError(
            "Training schema mismatch. "
            f"Missing={missing or '[]'}; Extra={extra or '[]'}; "
            f"ExpectedColumns={expected}; ActualColumns={actual}"
        )

    null_counts = (
        df[expected].isna().sum().to_dict()  # type: ignore[attr-defined]
    )
    cols_with_nulls = {k: int(v) for k, v in null_counts.items() if int(v) > 0}
    if cols_with_nulls:
        raise ValueError(f"Training data has nulls in required columns: {cols_with_nulls}")


def validate_inference_schema(df, strict: bool = False) -> None:
    """
    Ensures inference input matches expected feature names.

    - strict=False: allows missing/extra columns (best-effort inference) but validates any
      present expected columns for nulls.
    - strict=True: requires exactly the 23 features and nothing else, and no nulls.
    """
    expected = get_all_features()
    actual = list(map(str, getattr(df, "columns", [])))

    expected_set = _as_set(expected)
    actual_set = _as_set(actual)

    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)

    if strict and missing:
        raise ValueError(
            f"Inference schema missing required features: {missing}. "
            f"ExpectedFeatures={expected}; ActualColumns={actual}"
        )

    if strict and extra:
        raise ValueError(
            f"Inference schema has unexpected extra columns (strict=True): {extra}. "
            f"ExpectedFeatures={expected}; ActualColumns={actual}"
        )

    cols_to_check = [c for c in expected if c in actual_set]
    if cols_to_check:
        null_counts = df[cols_to_check].isna().sum().to_dict()  # type: ignore[attr-defined]
        cols_with_nulls = {k: int(v) for k, v in null_counts.items() if int(v) > 0}
        if cols_with_nulls:
            raise ValueError(
                f"Inference data has nulls in provided expected columns: {cols_with_nulls}"
            )


def freeze_contract(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(FEATURE_CONTRACT, p)
    return p


def load_frozen_contract(path: str | Path) -> Dict[str, Any]:
    return dict(joblib.load(Path(path)))


def validate_contract_consistency(frozen: Mapping[str, Any]) -> None:
    """
    Validates the saved contract matches the current contract.
    """
    frozen_num = list(frozen.get("numerical_features", []))
    frozen_cat = list(frozen.get("categorical_features", []))
    frozen_target = str(frozen.get("target", ""))

    if frozen_target != get_target():
        raise ValueError(
            f"Frozen target mismatch. Frozen={frozen_target!r} Current={get_target()!r}"
        )

    if frozen_num != get_numerical_features():
        raise ValueError(
            "Frozen numerical feature list mismatch. "
            f"Frozen={frozen_num} Current={get_numerical_features()}"
        )

    if frozen_cat != get_categorical_features():
        raise ValueError(
            "Frozen categorical feature list mismatch. "
            f"Frozen={frozen_cat} Current={get_categorical_features()}"
        )


def get_distance_category(distance_km: float) -> str:
    d = float(distance_km)
    if d <= 5:
        return "local"
    if d <= 15:
        return "city"
    if d <= 30:
        return "long_range"
    return "extreme"


def get_weather_encoded(weather: str) -> float:
    """
    Mapping required by the feature contract.
    """
    w = (weather or "").strip().lower()
    mapping = {
        "clear": 0.0,
        "cloudy": 1.0,
        "haze": 1.5,
        "rainy": 2.0,
        "stormy": 3.0,
    }
    return float(mapping.get(w, 1.0))


def get_is_rainy(weather: str) -> float:
    w = (weather or "").strip().lower()
    return 1.0 if w in {"rainy", "stormy"} else 0.0

