"""
kitchen_app.py  –  Kitchen / Chef Dashboard
Food Delivery DSS  |  Port 8502

Responsibilities:
  1. Sidebar: manage chef headcount per station.
  2. Section 1: incoming orders awaiting Chef confirmation.
     - Show system-suggested prep time (from item base times).
     - Chef adjusts via number_input and clicks "Confirm & Start".
     - Saves confirmed_prep_time to DB.
  3. Section 2: live item-level tracking with "Mark Ready" buttons.

Run:
    streamlit run Dss/kitchen_app.py --server.port 8502
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from db_manager import DatabaseManager

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Kitchen Dashboard 🍳", page_icon="🍳",
                   layout="wide", initial_sidebar_state="expanded")

st_autorefresh(interval=10_000, key="kitchen_refresh")

# ── DB ────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager()

db = get_db()

_STATUS_ICON = {"Pending": "🟡", "Cooking": "🔵", "Ready": "🟢"}

def _badge(status: str) -> str:
    return f"{_STATUS_ICON.get(status, '⚪')} {status}"

# ── Sidebar – Staffing ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🍳 Kitchen Configuration")
    st.caption("Set active chef headcount per station.")
    st.markdown("---")

    try:
        staffing = db.get_staffing()
    except Exception as exc:
        st.error(f"❌ Could not load staffing: {exc}")
        staffing = []

    if not staffing:
        st.info("No stations found in the database.")

    for row in staffing:
        station = row["station_name"]
        current = int(row["chef_count"])
        new_count = st.number_input(
            label     = station.replace("_", " ").title(),
            min_value = 1,
            max_value = 10,
            value     = current,
            step      = 1,
            key       = f"chef_{station}",
        )
        if new_count != current:
            try:
                db.update_staffing(station, new_count)
                st.toast(f"✅ {station} → {new_count} chef(s).", icon="✅")
            except Exception as exc:
                st.error(f"Failed to update {station}: {exc}")

    st.markdown("---")
    st.caption("🔄 Auto-refreshes every 10 seconds.")

# ── Section 1 – Pending Orders (Chef Confirmation) ────────────────────────────
st.markdown("## 👨‍🍳 Orders Awaiting Chef Confirmation")
st.caption("Review the suggested prep time, adjust if needed, then click **Confirm & Start**.")

try:
    pending = db.get_pending_orders_for_chef()
except Exception as exc:
    st.error(f"❌ Could not load pending orders: {exc}")
    pending = []

if not pending:
    st.success("✅ No orders waiting for confirmation.")
else:
    for order in pending:
        oid       = order["order_id"]
        suggested = float(order.get("suggested_prep_time") or 15.0)
        address   = order.get("customer_address", "—")
        rtype     = order.get("restaurant_type", "—")

        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.markdown(f"### 🧾 `{oid}`")
            h2.caption(f"📍 {address}")

            c1, c2 = st.columns(2)
            c1.metric("🤖 System Suggested Prep", f"{suggested:.0f} min")
            c2.metric("🍽️ Restaurant Type", rtype)
            st.markdown("---")

            confirmed_val = st.number_input(
                label     = "✏️ Confirm / Adjust Prep Time (min)",
                min_value = 1.0,
                max_value = 120.0,
                value     = float(round(suggested)),
                step      = 1.0,
                key       = f"prep_{oid}",
                help      = "Adjust if the kitchen is busier or faster than usual.",
            )

            if st.button("🚀 Confirm & Start", key=f"confirm_{oid}",
                         type="primary", use_container_width=True):
                try:
                    db.confirm_prep_time(oid, confirmed_val)
                    st.toast(
                        f"✅ {oid} confirmed — prep: {confirmed_val:.0f} min. "
                        "Manager will now calculate the final delivery ETA.",
                        icon="✅",
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to confirm: {exc}")

st.markdown("---")

# ── Section 2 – Live Item Tracking ───────────────────────────────────────────
st.markdown("## 📋 Live Order Items")

try:
    active = db.get_active_orders()
except Exception as exc:
    st.error(f"❌ Could not load orders: {exc}")
    active = []

if not active:
    st.success("✅ All caught up — no active items in the kitchen.")
else:
    grouped: dict[str, list[dict]] = {}
    for item in active:
        grouped.setdefault(item["order_id"], []).append(item)

    for oid, items in grouped.items():
        with st.container(border=True):
            st.markdown(f"### 🧾 Order `{oid}`")
            hdr = st.columns([2, 1, 2, 1, 1])
            for col, label in zip(hdr, ["**Item**","**Qty**","**Station**","**Status**","**Action**"]):
                col.markdown(label)
            st.divider()

            for item in items:
                c0, c1, c2, c3, c4 = st.columns([2, 1, 2, 1, 1])
                c0.write(item["item_name"])
                c1.write(item["quantity"])
                c2.write(item["station_name"].replace("_", " ").title())
                c3.write(_badge(item["status"]))
                if c4.button("✅ Ready", key=f"done_{oid}_{item['item_name']}",
                             use_container_width=True):
                    try:
                        db.complete_item(oid, item["item_name"])
                        # Check if ALL items for this order are now Ready
                        # If yes, update order status to Ready
                        import psycopg2
                        conn = psycopg2.connect(
                            host="localhost", port=5555,
                            database="food_delivery",
                            user="root", password="root"
                        )
                        with conn.cursor() as cur:
                            # Count total vs ready items for this order
                            cur.execute("""
                                SELECT
                                    COUNT(*) as total,
                                    SUM(CASE WHEN status = 'Ready' THEN 1 ELSE 0 END) as ready
                                FROM live_orders
                                WHERE order_id = %s
                            """, (oid,))
                            row = cur.fetchone()
                            total, ready = row[0], row[1]
                            # If all items ready → update order to Ready
                            if total > 0 and ready >= total:
                                cur.execute("""
                                    UPDATE orders
                                    SET status = 'Ready'
                                    WHERE order_id = %s
                                """, (oid,))
                        conn.commit()
                        conn.close()
                        st.toast(f"✅ {item['item_name']} marked Ready!", icon="✅")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed: {exc}")
