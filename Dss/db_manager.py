"""
db_manager.py
-------------
Database access layer for the Food Delivery DSS kitchen backend.
Uses psycopg2 with explicit open/close per method (Docker-safe, no connection pooling required).
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ── Connection config ─────────────────────────────────────────────────────────
_DSN = {
    "host":     "localhost",
    "port":     5555,
    "dbname":   "food_delivery",
    "user":     "root",
    "password": "root",
}


class DatabaseManager:
    """
    Thin data-access wrapper around the Food Delivery DSS PostgreSQL schema.

    Every public method opens a fresh connection, executes its query inside a
    transaction, and closes the connection on exit — safe for Docker/Streamlit
    where long-lived connections can silently drop.
    """

    # ── Internal helpers ──────────────────────────────────────────────────────

    @contextmanager
    def _get_conn(self):
        """Yield an open psycopg2 connection; commit or rollback on exit."""
        conn = None
        try:
            conn = psycopg2.connect(**_DSN)
            yield conn
            conn.commit()
        except psycopg2.Error as exc:
            if conn:
                conn.rollback()
            logger.error("Database error: %s", exc)
            raise
        finally:
            if conn and not conn.closed:
                conn.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_staffing(self) -> list[dict]:
        """
        Return all stations with their current chef count.

        Returns
        -------
        list[dict]
            Each dict has keys: station_name, chef_count.
        """
        sql = """
            SELECT station_name, chef_count
            FROM   kitchen_staffing
            ORDER  BY station_name;
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]

    def update_staffing(self, station: str, count: int) -> None:
        """
        Update the chef count for a station and stamp updated_at.

        Parameters
        ----------
        station : str
            station_name primary key value.
        count : int
            New chef headcount (must be >= 1).
        """
        if count < 1:
            raise ValueError(f"chef_count must be >= 1, got {count}")

        sql = """
            UPDATE kitchen_staffing
            SET    chef_count = %s,
                   updated_at = %s
            WHERE  station_name = %s;
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (count, datetime.now(timezone.utc), station))
                if cur.rowcount == 0:
                    logger.warning("update_staffing: station '%s' not found.", station)

    def get_active_orders(self) -> list[dict]:
        """
        Return all order items that are not yet Ready, oldest first.

        Returns
        -------
        list[dict]
            Keys: order_id, item_name, station_name, quantity, status.
        """
        sql = """
            SELECT order_id,
                   item_name,
                   station_name,
                   quantity,
                   status
            FROM   live_orders
            WHERE  status != 'Ready'
            ORDER  BY created_at ASC;
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]

    def complete_item(self, order_id: str, item_name: str) -> None:
        """
        Mark a specific order item as Ready and zero its remaining_time.

        Parameters
        ----------
        order_id  : str  Business-level order reference.
        item_name : str  Name of the menu item to complete.
        """
        sql = """
            UPDATE live_orders
            SET    status         = 'Ready',
                   remaining_time = 0
            WHERE  order_id  = %s
              AND  item_name = %s
              AND  status   != 'Ready';
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (order_id, item_name))
                if cur.rowcount == 0:
                    logger.warning(
                        "complete_item: no active row for order_id=%s item=%s",
                        order_id, item_name,
                    )

    def get_station_workload(self) -> dict[str, float]:
        """
        Return total remaining workload (minutes) per active station
        from the station_metrics view.

        Returns
        -------
        dict[str, float]
            e.g. {'grill': 30.0, 'fryer': 5.0}
        """
        sql = "SELECT station_name, total_workload FROM station_metrics;"
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return {row["station_name"]: float(row["total_workload"])
                        for row in cur.fetchall()}

    def insert_order_items(self, order_id: str, items: list[dict]) -> None:
        """
        Insert multiple order-item rows into live_orders in a single transaction.

        Parameters
        ----------
        order_id : str
            Business-level order reference.
        items : list[dict]
            Each dict must have keys:
            item_name, station_name, quantity, prep_time_assigned.
            Optional: suggested_prep_time.
        """
        sql = """
            INSERT INTO live_orders
                (order_id, item_name, station_name, quantity,
                 prep_time_assigned, remaining_time, suggested_prep_time, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pending');
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for item in items:
                    assigned = item["prep_time_assigned"]
                    cur.execute(sql, (
                        order_id,
                        item["item_name"],
                        item["station_name"],
                        item["quantity"],
                        assigned,
                        assigned,                              # remaining = assigned at creation
                        item.get("suggested_prep_time", assigned),
                    ))

    # ── Order header (orders table) ───────────────────────────────────────────

    def create_order_header(self, order: dict) -> None:
        """
        Insert a row into the orders header table.

        Parameters
        ----------
        order : dict
            Required keys: order_id, customer_address, latitude, longitude,
                           restaurant_type, ml_travel_prediction.
        """
        sql = """
            INSERT INTO orders
                (order_id, customer_address, latitude, longitude,
                 restaurant_type, ml_travel_prediction, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
            ON CONFLICT (order_id) DO NOTHING;
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    order["order_id"],
                    order["customer_address"],
                    order["latitude"],
                    order["longitude"],
                    order["restaurant_type"],
                    order.get("ml_travel_prediction"),
                ))

    def get_pending_orders_for_chef(self) -> list[dict]:
        """
        Return orders that have no confirmed_prep_time yet (Chef action needed).

        Returns
        -------
        list[dict]
            Keys: order_id, customer_address, restaurant_type,
                  ml_travel_prediction, suggested_prep_time, created_at.
        """
        sql = """
            SELECT
                o.order_id,
                o.customer_address,
                o.restaurant_type,
                o.ml_travel_prediction,
                MAX(lo.suggested_prep_time)  AS suggested_prep_time,
                o.created_at
            FROM  orders     o
            JOIN  live_orders lo USING (order_id)
            WHERE o.confirmed_prep_time IS NULL
              AND o.status = 'Pending'
            GROUP BY o.order_id, o.customer_address, o.restaurant_type,
                     o.ml_travel_prediction, o.created_at
            ORDER BY o.created_at ASC;
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]

    def confirm_prep_time(self, order_id: str, confirmed_prep_time: float) -> None:
        """
        Chef confirms the prep time for an order.
        Sets confirmed_prep_time, total_eta, status → Preparing, and confirmed_at.

        Parameters
        ----------
        order_id           : str
        confirmed_prep_time: float  Minutes confirmed by the Chef.
        """
        sql = """
            UPDATE orders
            SET    confirmed_prep_time = %s,
                   total_eta           = %s + COALESCE(ml_travel_prediction, 0),
                   status              = 'Preparing',
                   confirmed_at        = NOW()
            WHERE  order_id = %s;
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (confirmed_prep_time, confirmed_prep_time, order_id))
                if cur.rowcount == 0:
                    logger.warning("confirm_prep_time: order_id=%s not found.", order_id)

    def get_manager_map_data(self) -> list[dict]:
        """
        Return all active orders with lat/lng and ETA data for the Manager Map.
        """
        sql = """
            SELECT *
            FROM   manager_order_view
            WHERE  order_status NOT IN ('Delivered')
            ORDER  BY created_at DESC;
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]

    def get_order_eta(self, order_id: str) -> dict | None:
        """
        Return the current ETA fields for a single order.

        Returns
        -------
        dict with keys: confirmed_prep_time, ml_travel_prediction, total_eta, status.
        None if order not found.
        """
        sql = """
            SELECT confirmed_prep_time, ml_travel_prediction, total_eta, status
            FROM   orders
            WHERE  order_id = %s;
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (order_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def update_order_eta(self, order_id: str,
                         ml_travel_prediction: float,
                         total_eta: float) -> None:
        """
        Manager writes the ML-predicted travel time and final total ETA
        back to the orders table after running the model.
        """
        sql = """
            UPDATE orders
            SET    ml_travel_prediction = %s,
                   total_eta            = %s
            WHERE  order_id = %s;
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (ml_travel_prediction, total_eta, order_id))
                if cur.rowcount == 0:
                    logger.warning("update_order_eta: order_id=%s not found.", order_id)

    def get_area_density(self, latitude: float, longitude: float) -> str:
        """
        Resolve area_density for a customer location using the existing
        get_nearest_zone() PostgreSQL function.

        Calls the DB-side Haversine lookup — no rule-based logic, no string
        matching, no Google API. Returns 'unknown' if the nearest zone is
        more than 5 km away (handled inside the SQL function itself).

        Parameters
        ----------
        latitude  : float  Customer delivery latitude.
        longitude : float  Customer delivery longitude.

        Returns
        -------
        str
            One of: 'residential', 'commercial', 'mixed', 'unknown'
        """
        sql = "SELECT area_density FROM get_nearest_zone(%s, %s) LIMIT 1;"
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (latitude, longitude))
                row = cur.fetchone()
                if row is None:
                    logger.warning(
                        "get_area_density: no result for (%.6f, %.6f) — defaulting to 'unknown'.",
                        latitude, longitude,
                    )
                    return "unknown"
                return str(row[0])

    def clear_all_orders(self) -> None:
        """
        Hard-reset: truncate live_orders and orders tables, restarting all
        sequences. Use only from the Manager app's maintenance panel.
        CASCADE handles the FK from live_orders → orders automatically.
        """
        sql = "TRUNCATE TABLE live_orders, orders RESTART IDENTITY CASCADE;"
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("clear_all_orders: all order data wiped.")
