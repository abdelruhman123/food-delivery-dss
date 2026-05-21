"""
runtime_utils.py
----------------
Shared runtime helpers for the Food Delivery DSS.

These functions bridge the gap between operational data formats and the
ML feature schema defined in feature_contract.py.

Functions
---------
normalize_restaurant_type(value)
    Convert kitchen/operational restaurant type strings to the ML schema
    values expected by the trained model and fct_orders.

Usage
-----
Import wherever restaurant_type enters the ML feature vector:

    from runtime_utils import normalize_restaurant_type

    ml_restaurant_type = normalize_restaurant_type(order["restaurant_type"])
"""

import logging

logger = logging.getLogger(__name__)

# ── Restaurant type mapping ───────────────────────────────────────────────────
# Left side  : values used in menu_data.json and operational order records
# Right side : values used in public.raw_deliveries, fct_orders, and the ML model
#
# ML valid values (from fct_orders WHERE clause and feature_contract.py):
#   fast_food | casual | fine_dine | cafe

_RESTAURANT_TYPE_MAP: dict[str, str] = {
    # Canonical operational names → ML schema names
    "Fast Food":     "fast_food",
    "Casual Dining": "casual",
    "Fine Dining":   "fine_dine",
    "Cafe":          "cafe",
    # Lowercase variants (defensive)
    "fast food":     "fast_food",
    "casual dining": "casual",
    "fine dining":   "fine_dine",
    "cafe":          "cafe",
    # Already-normalised pass-through (idempotent)
    "fast_food":     "fast_food",
    "casual":        "casual",
    "fine_dine":     "fine_dine",
}


def normalize_restaurant_type(value: str) -> str:
    """
    Convert an operational restaurant type string to the ML schema value.

    Parameters
    ----------
    value : str
        Restaurant type as stored in the operational system or menu_data.json.
        Examples: "Fast Food", "Fine Dining", "Casual Dining", "Cafe"

    Returns
    -------
    str
        Normalised value matching the ML model's training schema.
        One of: 'fast_food', 'casual', 'fine_dine', 'cafe'

    Raises
    ------
    ValueError
        If the value cannot be mapped and no safe fallback exists.
        Callers should catch this and handle gracefully (e.g. default to
        'fast_food' with a warning, or reject the request).

    Examples
    --------
    >>> normalize_restaurant_type("Fast Food")
    'fast_food'
    >>> normalize_restaurant_type("Fine Dining")
    'fine_dine'
    >>> normalize_restaurant_type("fast_food")   # already normalised
    'fast_food'
    """
    normalised = _RESTAURANT_TYPE_MAP.get(value)

    if normalised is not None:
        return normalised

    # Case-insensitive fallback
    normalised = _RESTAURANT_TYPE_MAP.get(value.strip())
    if normalised is not None:
        return normalised

    logger.error(
        "normalize_restaurant_type: unknown value '%s'. "
        "Valid inputs: %s",
        value,
        list(_RESTAURANT_TYPE_MAP.keys()),
    )
    raise ValueError(
        f"Unknown restaurant_type '{value}'. "
        f"Valid values: {sorted(set(_RESTAURANT_TYPE_MAP.values()))}"
    )
