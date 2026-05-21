"""
customer_app.py  –  Customer Ordering Screen
Food Delivery DSS  |  Port 8501

Responsibilities:
  1. Browse menu, build cart.
  2. Enter delivery address (geocoded to lat/lng).
  3. Place order → saved to PostgreSQL (no ML here).
  4. Poll DB every 10 s; show Total ETA once Manager runs prediction.

Run:
    streamlit run Dss/customer_app.py --server.port 8501
"""

import json, uuid
from pathlib import Path

import streamlit as st
import googlemaps
from streamlit_autorefresh import st_autorefresh

from db_manager import DatabaseManager
from backend_logic import calculate_prep_time  # ENHANCED: Import dynamic prep time calculator

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Order Now 🍔", page_icon="🍔",
                   layout="wide", initial_sidebar_state="expanded")

st_autorefresh(interval=10_000, key="cust_refresh")

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.price-tag{font-size:1.05rem;font-weight:700;color:#cba6f7;}
.eta-wait{display:inline-block;background:#374151;color:#9ca3af;
          font-size:.78rem;border-radius:20px;padding:2px 10px;}
.eta-ok  {display:inline-block;background:#a6e3a1;color:#1e1e2e;
          font-weight:700;font-size:.78rem;border-radius:20px;padding:2px 10px;}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
_CONFIG_PATH    = Path(__file__).parent / "menu_data.json"
GOOGLE_MAPS_KEY = "YOUR_GOOGLE_MAPS_API_KEY"
GRID_COLS       = 3

_PRICES: dict[str, float] = {
    "Burger":5.99,"Cheeseburger":6.49,"Fried Chicken":7.99,
    "Chicken Nuggets":4.99,"Fries":2.49,"Onion Rings":3.29,
    "Pizza":8.99,"Soft Drink":1.49,"Ribeye Steak":24.99,
    "Beef Wellington":34.99,"Grilled Salmon":19.99,"Lamb Chops":22.99,
    "Risotto":14.99,"Lobster Tail":29.99,"Gourmet Salad":9.99,
    "Truffle Pasta":16.99,"Pasta Alfredo":11.99,"Chicken Panne":12.99,
    "Club Sandwich":8.99,"Grilled Chicken":10.99,"Fish and Chips":11.49,
    "Lentil Soup":4.99,"Tacos":7.99,"Margherita Pizza":9.99,
    "Espresso":2.49,"Latte":3.99,"Cappuccino":3.99,"Iced Coffee":3.49,
    "Croissant":2.99,"Cheese Cake":4.49,"Panini":6.99,"Fresh Juice":3.99,
}

# ── Cached resources ──────────────────────────────────────────────────────────
@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager()

@st.cache_resource
def get_gmaps() -> googlemaps.Client:
    return googlemaps.Client(key=GOOGLE_MAPS_KEY)

@st.cache_data(ttl=120)
def load_menu() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)

def geocode_address(address: str):
    """Return (lat, lng) or None."""
    if not address.strip():
        return None
    try:
        res = get_gmaps().geocode(address)
        if res:
            loc = res[0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception:
        pass
    return None

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"cart":{}, "order_placed":False, "last_order_id":None,
             "delivery_lat":None, "delivery_lng":None, "delivery_addr":""}.items():
    if k not in st.session_state:
        st.session_state[k] = v

db         = get_db()
menu       = load_menu()
menu_items = menu.get("menu_items", {})

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🍔 Your Order")
    st.markdown("---")

    restaurant_type = st.selectbox(
        "Restaurant type",
        options=list(menu.get("restaurant_types", {}).keys()),
        index=0,
    )

    st.markdown("### 📍 Delivery Address")
    addr_input = st.text_input(
        "Your address",
        placeholder="e.g. 15 Tahrir Square, Cairo",
        value=st.session_state.delivery_addr,
    )
    if st.button("📍 Confirm Address", use_container_width=True):
        coords = geocode_address(addr_input)
        if coords:
            st.session_state.delivery_lat  = coords[0]
            st.session_state.delivery_lng  = coords[1]
            st.session_state.delivery_addr = addr_input
            st.success(f"📌 {coords[0]:.4f}, {coords[1]:.4f}")
        else:
            st.error("❌ Address not found.")

    st.markdown("---")
    st.markdown("### 🛒 Cart")

    if not st.session_state.cart:
        st.caption("Your cart is empty.")
    else:
        total_price = 0.0
        for name, qty in st.session_state.cart.items():
            price = _PRICES.get(name, 0.0) * qty
            total_price += price
            st.write(f"**{name}** × {qty}  —  ${price:.2f}")

        st.markdown("---")
        st.markdown(f"**Subtotal: ${total_price:.2f}**")

        if st.session_state.delivery_lat is None:
            st.warning("⚠️ Confirm your delivery address to place the order.")

        col_clear, col_order = st.columns(2)
        if col_clear.button("🗑️ Clear", use_container_width=True):
            st.session_state.cart         = {}
            st.session_state.order_placed = False
            st.rerun()

        if col_order.button(
            "✅ Place Order", type="primary",
            use_container_width=True,
            disabled=(st.session_state.delivery_lat is None),
        ):
            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            try:
                # ENHANCED: Get current station workload for dynamic prep time calculation
                station_workload = db.get_station_workload()
                
                # ENHANCED: Calculate dynamic prep time using backend_logic
                order_items_list = [[name, qty] for name, qty in st.session_state.cart.items()]
                
                try:
                    dynamic_prep_time, bottleneck, debug_info = calculate_prep_time(
                        restaurant_type=restaurant_type,
                        order_items=order_items_list,
                        station_workload=station_workload
                    )
                except Exception as calc_err:
                    st.warning(f"⚠️ Dynamic calculation failed: {calc_err}. Using base times.")
                    dynamic_prep_time = None
                    debug_info = {}
                
                # Create order header
                db.create_order_header({
                    "order_id":             order_id,
                    "customer_address":     st.session_state.delivery_addr,
                    "latitude":             st.session_state.delivery_lat,
                    "longitude":            st.session_state.delivery_lng,
                    "restaurant_type":      restaurant_type,
                    "ml_travel_prediction": None,   # Manager fills this
                })
                
                # ENHANCED: Create order items with dynamic prep times
                rows = []
                for name, qty in st.session_state.cart.items():
                    item_cfg  = menu_items.get(name, {})
                    base_time = float(item_cfg.get("base_prep_time", 10))
                    
                    # Use dynamic prep time if available, otherwise fall back to base
                    suggested_time = dynamic_prep_time if dynamic_prep_time else base_time
                    
                    rows.append({
                        "item_name":           name,
                        "station_name":        item_cfg.get("station", "grill"),
                        "quantity":            qty,
                        "prep_time_assigned":  suggested_time,  # ENHANCED: Dynamic time
                        "suggested_prep_time": suggested_time,  # ENHANCED: Dynamic time
                    })
                
                db.insert_order_items(order_id, rows)
                st.session_state.last_order_id = order_id
                st.session_state.order_placed  = True
                st.session_state.cart          = {}
                
                # ENHANCED: Show workload impact info
                if dynamic_prep_time and debug_info:
                    st.toast(
                        f"✅ Order placed! Dynamic prep time: {dynamic_prep_time:.0f} min "
                        f"(Bottleneck: {bottleneck})",
                        icon="✅"
                    )
                else:
                    st.toast(f"✅ Order {order_id} placed successfully!", icon="✅")

                # Show ETA if already available
                try:
                    eta_data = db.get_order_eta(order_id)
                    if eta_data and eta_data.get("total_eta"):
                        st.info(f"Estimated delivery: {float(eta_data['total_eta']):.0f} min")
                except Exception:
                    pass

                st.rerun()
            except Exception as exc:
                st.error(f"❌ Order failed: {exc}")

# ── Order tracking banner ─────────────────────────────────────────────────────
if st.session_state.order_placed and st.session_state.last_order_id:
    oid = st.session_state.last_order_id
    try:
        eta_data = db.get_order_eta(oid)
    except Exception:
        eta_data = None

    total_eta = eta_data.get("total_eta")   if eta_data else None
    status    = eta_data.get("status","Pending") if eta_data else "Pending"

    with st.container(border=True):
        st.markdown(f"### 📦 Order `{oid}` — Tracking")
        t1, t2, t3 = st.columns(3)
        t1.metric("Status", status)
        if total_eta is not None:
            t2.metric("⏱️ Total ETA", f"{float(total_eta):.0f} min")
            
            st.success(
                f"✅ Delivery confirmed! Estimated arrival in "
                f"**{float(total_eta):.0f} minutes**."
            )
        else:
            t2.metric("⏱️ Total ETA", "Calculating…")
            
            
    st.markdown("---")

# ── Menu Grid ─────────────────────────────────────────────────────────────────
st.title("🍔 Modern Food Delivery — Order Now")
st.caption(f"Kitchen: **{restaurant_type}**  ·  ETA calculated by the Manager after order placement.")
st.markdown("---")

item_names = list(menu_items.keys())
for row_items in [item_names[i:i+GRID_COLS] for i in range(0, len(item_names), GRID_COLS)]:
    cols = st.columns(GRID_COLS, gap="medium")
    for col, item_name in zip(cols, row_items):
        item_cfg = menu_items[item_name]
        price    = _PRICES.get(item_name, 0.0)
        with col:
            with st.container(border=True):
                st.markdown(f"**{item_name}**")
                st.markdown(
                    f"<span class='price-tag'>${price:.2f}</span>"
                    f"&nbsp;&nbsp;<span class='eta-wait'>ETA after order</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Station: {item_cfg['station'].title()}  ·  "
                           f"Base: {item_cfg['base_prep_time']} min")
                in_cart = st.session_state.cart.get(item_name, 0)
                if in_cart:
                    c1, c2 = st.columns([2, 1])
                    c1.success(f"✅ × {in_cart}")
                    if c2.button("➕", key=f"add_{item_name}", use_container_width=True):
                        st.session_state.cart[item_name] = in_cart + 1
                        st.rerun()
                else:
                    if st.button("🛒 Add", key=f"add_{item_name}", use_container_width=True):
                        st.session_state.cart[item_name] = 1
                        st.rerun()
