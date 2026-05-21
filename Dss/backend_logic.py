"""
backend_logic.py
----------------
Real-time preparation time calculator for the Food Delivery DSS.

Designed to run inside Docker, with workload data sourced from PostgreSQL.
Configuration is loaded from Dss/menu_data.json.

ENHANCED: True dynamic queue-based kitchen simulation with:
- Stronger workload impact on queue times
- Chef scaling that significantly affects throughput
- Realistic concurrency effects for multiple orders
"""

import json
import math
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
# ENHANCED: Increased overlap factor for stronger workload impact
OVERLAP_FACTOR = 1.2  # Was 0.7 - now workload has 120% impact (accounts for context switching)

# ENHANCED: Minimum queue time multiplier when workload exists
MIN_QUEUE_MULTIPLIER = 0.3  # Even with many chefs, some queue delay exists

# ENHANCED: Congestion penalty - kicks in when workload is high
CONGESTION_THRESHOLD = 30.0  # minutes of workload
CONGESTION_PENALTY = 0.15    # 15% additional delay per 30min of excess workload

_CONFIG_PATH   = Path(__file__).parent / "menu_data.json"

# ── Config loader (module-level cache) ────────────────────────────────────────
_config: Optional[dict] = None


def _load_config() -> dict:
    """Load and cache menu_data.json. Raises RuntimeError if unreadable."""
    global _config
    if _config is not None:
        return _config
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            _config = json.load(fh)
        logger.info("menu_data.json loaded from %s", _CONFIG_PATH)
        return _config
    except FileNotFoundError:
        raise RuntimeError(f"Configuration file not found: {_CONFIG_PATH}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {_CONFIG_PATH}: {exc}") from exc


# ── Core calculation ──────────────────────────────────────────────────────────

def calculate_prep_time(
    restaurant_type: str,
    order_items: list[list],
    station_workload: dict[str, float],
) -> tuple[float, str, dict]:
    """
    Calculate the real-time preparation time for an order with dynamic queue simulation.

    ENHANCED: This function now implements a true queue-based kitchen simulation where:
    - Workload has a strong, realistic impact on queue times
    - Chef count significantly affects throughput (more chefs = much faster)
    - Multiple concurrent orders create realistic congestion effects
    - System behaves like a real kitchen with shared resources

    Parameters
    ----------
    restaurant_type : str
        Restaurant category key matching menu_data.json
        (e.g. "Fast Food", "Fine Dining").
    order_items : list[list]
        Each element is [item_name: str, quantity: int],
        e.g. [['Burger', 2], ['Fries', 1]].
    station_workload : dict[str, float]
        Remaining prep-time load (minutes) per station for active orders,
        e.g. {'grill': 40, 'fryer': 10}.
        Missing stations are treated as 0 workload.

    Returns
    -------
    tuple[float, str, dict]
        (final_prep_time, bottleneck_station, debug_info)
        final_prep_time    – max item prep time across all stations, rounded to 2 dp.
        bottleneck_station – station name responsible for the longest delay.
        debug_info         – dict with detailed calculation breakdown for debugging.

    Raises
    ------
    ValueError
        If restaurant_type is not found in the configuration.
    """
    config = _load_config()

    # ── Validate restaurant type ──────────────────────────────────────────────
    restaurant_cfg = config.get("restaurant_types", {}).get(restaurant_type)
    if restaurant_cfg is None:
        available = list(config.get("restaurant_types", {}).keys())
        raise ValueError(
            f"Unknown restaurant_type '{restaurant_type}'. "
            f"Available: {available}"
        )

    stations_cfg: dict = restaurant_cfg.get("stations", {})
    menu_cfg: dict     = config.get("menu_items", {})

    item_times: list[tuple[float, str]] = []  # (prep_time, station)
    debug_info = {"items": [], "workload_impact": {}}

    for entry in order_items:
        # ── Parse order entry ─────────────────────────────────────────────────
        if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
            logger.warning("Skipping malformed order entry: %s", entry)
            continue

        item_name, quantity = entry[0], entry[1]

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            logger.warning("Invalid quantity for '%s': %s — defaulting to 1.", item_name, quantity)
            quantity = 1

        # ── Look up item config ───────────────────────────────────────────────
        item_cfg = menu_cfg.get(item_name)
        if item_cfg is None:
            logger.warning(
                "Item '%s' not found in menu_data.json — skipped.", item_name
            )
            continue

        station        = item_cfg["station"]
        base_prep_time = float(item_cfg["base_prep_time"])
        is_batch       = bool(item_cfg.get("batch", False))
        capacity       = int(item_cfg.get("capacity_per_batch", 1))

        # ── Station chef count ────────────────────────────────────────────────
        station_info = stations_cfg.get(station)
        if station_info is None:
            logger.warning(
                "Station '%s' (needed by '%s') not configured for '%s' — "
                "defaulting to 1 chef.",
                station, item_name, restaurant_type,
            )
            station_chefs = 1
        else:
            station_chefs = max(int(station_info.get("chefs", 1)), 1)

        # ── ENHANCED: Dynamic queue time calculation ──────────────────────────
        workload = float(station_workload.get(station, 0.0))
        
        # Base queue time: workload divided by chefs, with overlap factor
        base_queue = (workload / station_chefs) * OVERLAP_FACTOR
        
        # Minimum queue time: even with many chefs, some delay exists when busy
        min_queue = workload * MIN_QUEUE_MULTIPLIER if workload > 0 else 0
        
        # Congestion penalty: additional delay when station is heavily loaded
        if workload > CONGESTION_THRESHOLD:
            excess_workload = workload - CONGESTION_THRESHOLD
            congestion_penalty = (excess_workload / CONGESTION_THRESHOLD) * CONGESTION_PENALTY * workload
        else:
            congestion_penalty = 0.0
        
        # Final queue time: max of base and minimum, plus congestion
        queue_time = max(base_queue, min_queue) + congestion_penalty

        # ── Production cycles (batching) ──────────────────────────────────────
        if is_batch:
            cycles = math.ceil(quantity / capacity)
        else:
            cycles = quantity

        # ── Total item prep time ──────────────────────────────────────────────
        production_time = base_prep_time * cycles
        item_prep_time = queue_time + production_time
        item_times.append((item_prep_time, station))

        # ── Debug info ────────────────────────────────────────────────────────
        item_debug = {
            "item": item_name,
            "quantity": quantity,
            "station": station,
            "chefs": station_chefs,
            "workload": workload,
            "base_queue": round(base_queue, 2),
            "min_queue": round(min_queue, 2),
            "congestion_penalty": round(congestion_penalty, 2),
            "queue_time": round(queue_time, 2),
            "production_time": round(production_time, 2),
            "total_time": round(item_prep_time, 2),
        }
        debug_info["items"].append(item_debug)

        logger.debug(
            "%s x%d | station=%s | chefs=%d | workload=%.1f | "
            "base_queue=%.2f | min_queue=%.2f | congestion=%.2f | "
            "queue=%.2f | production=%.2f | total=%.2f",
            item_name, quantity, station, station_chefs, workload,
            base_queue, min_queue, congestion_penalty,
            queue_time, production_time, item_prep_time,
        )

    # ── Guard: no valid items ─────────────────────────────────────────────────
    if not item_times:
        logger.warning("No valid items found in order — returning 0.0 prep time.")
        return (0.0, "none", debug_info)

    # ── Parallel execution: bottleneck is the MAX ─────────────────────────────
    final_prep_time, bottleneck_station = max(item_times, key=lambda x: x[0])
    
    debug_info["final_prep_time"] = round(final_prep_time, 2)
    debug_info["bottleneck_station"] = bottleneck_station

    return (round(final_prep_time, 2), bottleneck_station, debug_info)
