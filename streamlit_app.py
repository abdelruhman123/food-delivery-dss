"""
streamlit_app.py  -  Manager / DSS Dashboard
Food Delivery Decision Support System
Port 8503

Tabs:
  1. Dashboard KPIs  — traffic breakdown, summary stats, recent orders, model info
  2. Live Orders Map — predict ETA per order, map pins, DB sync

ETA prediction is delegated entirely to eta_api.py (port 8000).
This app is responsible ONLY for:
  - Google Directions API call (distance_km + duration_traffic + traffic_level)
  - Sending the payload to POST /predict-eta
  - Displaying the hybrid ETA breakdown from the response

Run:
    streamlit run streamlit_app.py --server.port 8503
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import googlemaps
import pandas as pd
from sqlalchemy import create_engine, text

_DSS_DB_URL = "postgresql://root:root@localhost:5555/food_delivery"

# ── DSS sub-package on path ───────────────────────────────────────────────────
_DSS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dss")
if _DSS_DIR not in sys.path:
    sys.path.insert(0, _DSS_DIR)
from db_manager import DatabaseManager

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Delivery DSS - Manager",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Global ── */
.stApp { background-color: #0f1117; }

/* ── Main header ── */
.main-header {
    font-size: 1.8rem;
    font-weight: 800;
    text-align: center;
    padding: 1rem 1.5rem;
    background: linear-gradient(135deg, #4f8ef7 0%, #7c5cbf 100%);
    color: #fff;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    letter-spacing: 0.5px;
    box-shadow: 0 4px 20px rgba(79,142,247,0.3);
}

/* ── Section headers ── */
.section-header {
    font-size: 1.1rem;
    font-weight: 700;
    color: #4f8ef7;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.8rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid #4f8ef7;
}

/* ── KPI cards ── */
.kpi-card {
    background: #1e2130;
    border-radius: 12px;
    padding: 1.2rem;
    border: 1px solid #2d3348;
    text-align: center;
    box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}
.kpi-value {
    font-size: 2rem;
    font-weight: 800;
    color: #4f8ef7;
}
.kpi-label {
    font-size: 0.8rem;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-top: 0.3rem;
}

/* ── Status badges ── */
.badge-pending   { background:#f59e0b22; color:#f59e0b; padding:2px 10px; border-radius:20px; font-size:.78rem; font-weight:700; }
.badge-preparing { background:#3b82f622; color:#3b82f6; padding:2px 10px; border-radius:20px; font-size:.78rem; font-weight:700; }
.badge-ready     { background:#22c55e22; color:#22c55e; padding:2px 10px; border-radius:20px; font-size:.78rem; font-weight:700; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: #1e2130 !important;
    border-right: 1px solid #2d3348;
}
section[data-testid="stSidebar"] .stMarkdown h2 {
    color: #4f8ef7;
    font-size: 1.2rem;
}

/* ── Tab styling ── */
.stTabs [data-baseweb="tab-list"] {
    background: #1e2130;
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #9ca3af;
    border-radius: 8px;
    font-weight: 600;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #4f8ef7, #7c5cbf) !important;
    color: white !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #1e2130;
    border: 1px solid #2d3348;
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
[data-testid="stMetricValue"] { color: #ffffff; font-weight: 800; }
[data-testid="stMetricLabel"] { color: #9ca3af; font-size: 0.78rem; }

/* ── Dataframes ── */
[data-testid="stDataFrame"] {
    border: 1px solid #2d3348;
    border-radius: 10px;
    overflow: hidden;
}

/* ── Containers with border ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #1e2130 !important;
    border: 1px solid #2d3348 !important;
    border-radius: 12px !important;
    padding: 1rem !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #4f8ef7, #7c5cbf);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
    transition: opacity 0.2s;
}
.stButton > button:hover { opacity: 0.85; }

/* ── Alerts ── */
.stSuccess { background: #22c55e15; border-left: 4px solid #22c55e; }
.stWarning { background: #f59e0b15; border-left: 4px solid #f59e0b; }
.stError   { background: #ef444415; border-left: 4px solid #ef4444; }
.stInfo    { background: #4f8ef715; border-left: 4px solid #4f8ef7; }

/* ── Text inputs ── */
.stTextInput input {
    background-color: #2d3348 !important;
    color: #ffffff !important;
    border: 1px solid #4f8ef7 !important;
    border-radius: 8px !important;
}
.stTextInput input::placeholder { color: #6b7280 !important; }
.stTextInput input:focus {
    border-color: #7c5cbf !important;
    box-shadow: 0 0 0 2px rgba(124,91,191,0.3) !important;
}

/* ── All inputs general ── */
input, textarea, [data-baseweb="input"] {
    background-color: #2d3348 !important;
    color: #ffffff !important;
}

/* ── Force all text to be visible ── */
.stApp, .stApp * { color: #ffffff !important; }

/* ── Specific overrides ── */
p, span, label, div { color: #ffffff !important; }

/* ── Markdown text ── */
.stMarkdown p { color: #e2e8f0 !important; }

/* ── Captions ── */
.stCaption, [data-testid="stCaptionContainer"] { color: #9ca3af !important; }

/* ── Metric labels and values ── */
[data-testid="stMetricLabel"] { color: #9ca3af !important; }
[data-testid="stMetricValue"] { color: #ffffff !important; }
[data-testid="stMetricDelta"] { color: #22c55e !important; }

/* ── Dataframe text ── */
[data-testid="stDataFrame"] * { color: #ffffff !important; }

/* ── Tab text ── */
.stTabs [data-baseweb="tab"]  { color: #9ca3af !important; }
.stTabs [aria-selected="true"] { color: #ffffff !important; }

/* ── Sidebar text ── */
section[data-testid="stSidebar"] *        { color: #ffffff !important; }
section[data-testid="stSidebar"] .stCaption { color: #9ca3af !important; }

/* ── Input labels ── */
.stTextInput label, .stSelectbox label, .stNumberInput label { color: #9ca3af !important; }

/* ── Expander text ── */
.streamlit-expanderHeader { color: #ffffff !important; }

/* ── Success/Warning/Error/Info text ── */
.stSuccess, .stSuccess * { color: #22c55e !important; }
.stWarning, .stWarning * { color: #f59e0b !important; }
.stError,   .stError *   { color: #ef4444 !important; }
.stInfo,    .stInfo *    { color: #4f8ef7 !important; }

/* ── Fix white box next to Distance label ── */
.stTextInput input:disabled,
.stTextInput input[disabled],
input:read-only,
.stTextInput input[readonly] {
    background-color: #2d3348 !important;
    color: #ffffff !important;
    border: 1px solid #4f8ef7 !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
}

/* ── Fix white box in expander (feature list, API response) ── */
.streamlit-expanderContent {
    background-color: #1e2130 !important;
    border: 1px solid #2d3348 !important;
    color: #ffffff !important;
}
.streamlit-expanderContent * { color: #ffffff !important; }
[data-testid="stExpander"] {
    background-color: #1e2130 !important;
    border: 1px solid #2d3348 !important;
}
[data-testid="stExpander"] * { color: #ffffff !important; }

/* ── Fix st.write() white background ── */
[data-testid="stText"],
[data-testid="stMarkdownContainer"] {
    background-color: transparent !important;
    color: #ffffff !important;
}

/* ── Fix st.json() white background ── */
[data-testid="stJson"] {
    background-color: #1e2130 !important;
    border-radius: 8px !important;
    border: 1px solid #2d3348 !important;
}

/* ── Force expander content dark background ── */
div[data-testid="stExpanderDetails"] {
    background-color: #1e2130 !important;
}
div[data-testid="stExpanderDetails"] * {
    background-color: transparent !important;
    color: #ffffff !important;
}

/* ── Fix st.write() list items inside expander ── */
div[data-testid="stExpanderDetails"] ul,
div[data-testid="stExpanderDetails"] ol,
div[data-testid="stExpanderDetails"] li {
    background-color: transparent !important;
    color: #e2e8f0 !important;
}

/* ── Fix the expander border ── */
details {
    background-color: #1e2130 !important;
    border: 1px solid #2d3348 !important;
    border-radius: 8px !important;
}
details > div {
    background-color: #1e2130 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
ROOT            = os.path.dirname(os.path.abspath(__file__))
EGYPT_CENTER    = [30.0444, 31.2357]
PEAK_HOURS      = range(17, 21)
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "YOUR_GOOGLE_MAPS_API_KEY")
ETA_API_URL     = os.getenv("ETA_API_URL", "http://localhost:8000")

# ── Restaurant type normalizer ────────────────────────────────────────────────
_RTYPE_MAP = {
    "Fast Food": "fast_food", "fast_food": "fast_food",
    "Casual":    "casual",    "casual":    "casual",
    "Fine Dining":"fine_dine","fine_dine": "fine_dine",
    "Cafe":      "cafe",      "cafe":      "cafe",
}

def normalize_restaurant_type(rtype: str) -> str:
    return _RTYPE_MAP.get(rtype, "fast_food")

# ── Cached resources ──────────────────────────────────────────────────────────
@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager()

@st.cache_resource
def get_gmaps() -> googlemaps.Client:
    return googlemaps.Client(key=GOOGLE_MAPS_KEY)


# ── Cached DSS analytics queries ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def _get_hour_stats():
    engine = create_engine(_DSS_DB_URL)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT hour_of_day,
                   round(avg(delivery_time_min)::numeric, 1) AS avg_delivery,
                   count(*) AS total_orders
            FROM dbt_schema_marts.fct_orders
            GROUP BY hour_of_day ORDER BY hour_of_day
        """)).mappings().all()
    return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def _get_restaurant_perf():
    engine = create_engine(_DSS_DB_URL)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT f.restaurant_type,
                   round(avg(f.delivery_time_min)::numeric, 1)                   AS avg_delivery,
                   round(avg(f.prep_time_min)::numeric, 1)                        AS avg_prep,
                   round(avg(f.prep_time_min + f.delivery_time_min)::numeric, 1)  AS avg_total,
                   count(*) AS total_orders
            FROM dbt_schema_marts.fct_orders f
            GROUP BY f.restaurant_type ORDER BY avg_total ASC
        """)).mappings().all()
    return [dict(r) for r in rows]


@st.cache_data(ttl=60)
def _get_dim_restaurants():
    engine = create_engine(_DSS_DB_URL)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT restaurant_type,
                   round(avg_prep_time::numeric, 1) AS avg_prep_time_min
            FROM dim_restaurants ORDER BY avg_prep_time ASC
        """)).mappings().all()
    return [dict(r) for r in rows]


@st.cache_data(ttl=300)
def _get_api_schema():
    resp = requests.get(f"{os.getenv('ETA_API_URL', 'http://localhost:8000')}/schema", timeout=5)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=30)
def _get_api_health():
    resp = requests.get(f"{os.getenv('ETA_API_URL', 'http://localhost:8000')}/health", timeout=5)
    return resp.json() if resp.ok else {}


@st.cache_data(ttl=15)
def _get_orders():
    return get_db().get_manager_map_data()


@st.cache_resource
def get_engine():
    return create_engine(_DSS_DB_URL)

# ── Utility functions ─────────────────────────────────────────────────────────
def geocode(address: str):
    """
    Geocode using Google Maps Geocoding API (same geocoder as customer_app.py).
    Using Nominatim here caused ~1 km distance discrepancy vs Google Maps mobile
    because Nominatim snaps to different coordinate precision than Google.
    """
    if not address.strip():
        return None
    try:
        results = get_gmaps().geocode(address)
        if results:
            loc = results[0]["geometry"]["location"]
            return [loc["lat"], loc["lng"]]
    except Exception as exc:
        st.warning(f"Geocoding failed: {exc}")
    return None

def get_directions_data(origin: list, destination: list) -> dict:
    """
    Google Directions API (driving) with real-time traffic.
    Returns distance_km, traffic_level, polyline_pts, and raw durations.
    Raises RuntimeError on any failure — no silent fallback.
    """
    result = get_gmaps().directions(
        origin={"lat": origin[0], "lng": origin[1]},
        destination={"lat": destination[0], "lng": destination[1]},
        mode="driving",
        departure_time="now",
    )
    if not result:
        raise RuntimeError(
            "Google Directions API returned empty result. "
            "Verify the API key has Directions API enabled."
        )

    leg = result[0]["legs"][0]
    distance_km     = leg["distance"]["value"] / 1000.0
    duration_normal = leg["duration"]["value"] / 60.0

    if "duration_in_traffic" in leg:
        duration_traffic = leg["duration_in_traffic"]["value"] / 60.0
    else:
        duration_traffic = duration_normal

    traffic_ratio = duration_traffic / duration_normal if duration_normal > 0 else 1.0

    if traffic_ratio < 1.15:
        traffic_level = "low"
    elif traffic_ratio < 1.35:
        traffic_level = "medium"
    else:
        traffic_level = "high"

    raw_poly     = result[0]["overview_polyline"]["points"]
    decoded      = googlemaps.convert.decode_polyline(raw_poly)
    polyline_pts = [[p["lat"], p["lng"]] for p in decoded]

    return {
        "distance_km":      distance_km,
        "polyline_pts":     polyline_pts,
        "traffic_level":    traffic_level,
        "duration_normal":  duration_normal,
        "duration_traffic": duration_traffic,
        "traffic_ratio":    traffic_ratio,
    }

def call_eta_api(payload: dict) -> dict:
    """
    POST payload to eta_api /predict-eta.
    Returns the parsed JSON response.
    Raises RuntimeError on HTTP error or connection failure.
    """
    url = f"{ETA_API_URL}/predict-eta"
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach ETA API at {url}. "
            "Start it with: uvicorn eta_api:app --port 8000"
        )
    except requests.exceptions.HTTPError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        raise RuntimeError(f"ETA API error {exc.response.status_code}: {detail}")


@st.cache_data(ttl=30)
def fetch_dashboard_kpis() -> dict:
    """GET /dashboard-kpis from ETA API."""
    url = f"{ETA_API_URL}/dashboard-kpis"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Dashboard KPI fetch failed: {e}")

# ── Session state ─────────────────────────────────────────────────────────────
if "rest_address" not in st.session_state:
    st.session_state.rest_address = ""
if "rest_coords" not in st.session_state:
    st.session_state.rest_coords = EGYPT_CENTER[:]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style='text-align:center; padding:1rem 0;'>
  <div style='font-size:2.5rem;'>🚚</div>
  <div style='font-weight:800; font-size:1.1rem; color:#4f8ef7;'>Food Delivery DSS</div>
  <div style='font-size:0.75rem; color:#9ca3af;'>Manager Dashboard</div>
</div>
""", unsafe_allow_html=True)
    st.markdown("## Manager DSS")
    st.markdown("---")
    st.markdown("### Restaurant Address")
    rest_input = st.text_input(
        "Physical restaurant address",
        placeholder="e.g. Cairo Tower, Zamalek, Cairo",
        value=st.session_state.rest_address,
    )
    if st.button("Set Restaurant Location", use_container_width=True):
        coords = geocode(rest_input)
        if coords:
            st.session_state.rest_coords  = coords
            st.session_state.rest_address = rest_input
            st.success(f"Location set: {coords[0]:.4f}, {coords[1]:.4f}")
        else:
            st.error("Address not found.")
    if datetime.now().hour in PEAK_HOURS:
        st.warning("Peak hours (17-20). Expect higher delivery times.")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="main-header">Food Delivery Decision Support System</div>',
    unsafe_allow_html=True,
)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_dashboard, tab_map, tab_dss = st.tabs([
    "📊 Dashboard & Model Info",
    "🗺️ Live Orders Map",
    "🔍 DSS Insights",
])

# =============================================================================
# TAB 1 - Dashboard KPIs + Model Info
# =============================================================================
with tab_dashboard:
    # ── KPI section ───────────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>Live KPIs</div>", unsafe_allow_html=True)
    try:
        kpi_data = fetch_dashboard_kpis()
        summary  = kpi_data.get("summary", {})
        kpi_cols  = st.columns(4)
        kpi_items = [
            ("🛵 Total Orders",  summary.get("total_orders", "—")),
            ("⏱️ Avg Delivery",  f"{summary.get('overall_avg', '—')} min"),
            ("⚡ Fastest",       f"{summary.get('min_time', '—')} min"),
            ("🐢 Slowest",       f"{summary.get('max_time', '—')} min"),
        ]
        for col, (label, value) in zip(kpi_cols, kpi_items):
            col.markdown(f"""
<div class='kpi-card'>
  <div class='kpi-value'>{value}</div>
  <div class='kpi-label'>{label}</div>
</div>
""", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<div class='section-header'>Avg Delivery Time by Traffic Level</div>", unsafe_allow_html=True)
        traffic = kpi_data.get("traffic_breakdown", [])
        if traffic:
            import plotly.express as px
            df_t      = pd.DataFrame(traffic)
            color_map = {'low': '#22c55e', 'medium': '#f59e0b', 'high': '#ef4444'}
            df_t['color'] = df_t['traffic_level'].map(color_map)
            fig = px.bar(
                df_t,
                x='traffic_level',
                y='avg_delivery',
                color='traffic_level',
                color_discrete_map=color_map,
                labels={'traffic_level': 'Traffic Level', 'avg_delivery': 'Avg Delivery (min)'},
                template='plotly_dark',
            )
            fig.update_layout(
                paper_bgcolor='#1e2130',
                plot_bgcolor='#1e2130',
                font_color='#ffffff',
                showlegend=False,
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("<div class='section-header'>Recent 20 Orders</div>", unsafe_allow_html=True)
        recent = kpi_data.get("recent_orders", [])
        if recent:
            df_recent = pd.DataFrame(recent)
            df_recent = df_recent.rename(columns={
                'order_id':       '🆔 Order ID',
                'restaurant_type':'🍽️ Type',
                'status':         '📋 Status',
                'total_eta':      '⏱️ Total ETA',
                'created_at':     '🕐 Created At',
            })
            # Drop ML Travel column
            if 'ml_travel_prediction' in df_recent.columns:
                df_recent = df_recent.drop(columns=['ml_travel_prediction'])
            if '🧠 ML Travel' in df_recent.columns:
                df_recent = df_recent.drop(columns=['🧠 ML Travel'])
            if '⏱️ Total ETA' in df_recent.columns:
                df_recent['⏱️ Total ETA'] = df_recent['⏱️ Total ETA'].apply(
                    lambda x: f"{float(x):.1f} min" if x is not None else "—"
                )
            def color_status(val):
                colors = {
                    'Preparing': 'color: #3b82f6; font-weight: bold',
                    'Pending':   'color: #f59e0b; font-weight: bold',
                    'Ready':     'color: #22c55e; font-weight: bold',
                    'Delivered': 'color: #6b7280',
                }
                return colors.get(val, '')
            styled = df_recent.style.applymap(color_status, subset=['📋 Status'])
            st.dataframe(styled, use_container_width=True, height=400)
        else:
            st.info("No recent orders.")

    except RuntimeError as e:
        st.error(str(e))
        st.caption("Make sure `uvicorn eta_api:app --port 8000` is running.")

    # ── Model info section ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-header'>Model Info</div>", unsafe_allow_html=True)
    try:
        schema_data = _get_api_schema()
        health_data = _get_api_health()
        m1, m2, m3 = st.columns(3)
        m1.metric("Model Status",   health_data.get("status", "—").upper())
        m2.metric("Total Features", schema_data.get("total_features", "—"))
        m3.metric("Contract Ver.",  schema_data.get("version", "—"))
        with st.expander("Feature list", expanded=False):
            st.write(schema_data.get("features", []))
    except Exception as e:
        st.warning(f"Could not load model info from API: {e}")

# =============================================================================
# TAB 2 - Live Orders Map  (Manager DSS core)
# =============================================================================
with tab_map:
    st_autorefresh(interval=30_000, key="mgr_refresh")

    st.markdown("""
<div style='background:#1e2130; border-radius:10px; padding:0.8rem 1rem;
     margin-bottom:1rem; border-left:4px solid #4f8ef7;'>
  <span style='color:#4f8ef7; font-weight:700;'>Live Orders Map</span>
  <span style='color:#9ca3af; font-size:0.85rem; margin-left:1rem;'>Auto-refreshes every 10s</span>
</div>
""", unsafe_allow_html=True)

    # ── Fetch orders ──────────────────────────
    try:
        orders = _get_orders()
        db_ok  = True
    except Exception as e:
        st.error(f"DB error: {e}")
        orders, db_ok = [], False

    # ── KPI strip ─────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Active",    len(orders))
    k2.metric("Pending",   sum(1 for o in orders if o.get("order_status") == "Pending"))
    k3.metric("Preparing", sum(1 for o in orders if o.get("order_status") == "Preparing"))
    k4.metric("Ready",     sum(1 for o in orders if o.get("order_status") == "Ready"))
    st.markdown("---")

    # ── Pin helpers ───────────────────────────
    _PIN = {
        "Pending":   ("orange", "clock-o"),
        "Preparing": ("blue",   "fire"),
        "Ready":     ("green",  "check"),
        "Delivered": ("gray",   "truck"),
    }

    def _pin(status):
        return _PIN.get(status, ("red", "question"))

    def _popup_html(o):
        prep  = o.get("confirmed_prep_time")
        eta   = o.get("total_eta")
        ri    = int(o.get("ready_items") or 0)
        ti    = int(o.get("total_items") or 1)
        return (
            f"<b>{o['order_id']}</b><br>"
            f"Address: {o.get('customer_address', '-')}<br>"
            f"Prep: {f'{prep:.0f} min' if prep is not None else 'Awaiting chef'}<br>"
            f"<b>ETA: {f'{eta:.0f} min' if eta is not None else 'Pending'}</b><br>"
            f"Items: {ri}/{ti} ready"
        )

    col_map_v, col_cards = st.columns([3, 2], gap="large")

    # ── Map ───────────────────────────────────
    with col_map_v:
        if st.checkbox("Show Map", value=True, key="show_map"):
            lats = [float(o["latitude"])  for o in orders if o.get("latitude")  is not None]
            lngs = [float(o["longitude"]) for o in orders if o.get("longitude") is not None]
            center = ([sum(lats)/len(lats), sum(lngs)/len(lngs)] if lats else EGYPT_CENTER)

            m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")
            rest_c = st.session_state.rest_coords

            if st.session_state.rest_address:
                folium.Marker(
                    location=rest_c,
                    popup=folium.Popup(f"Restaurant: {st.session_state.rest_address}", max_width=220),
                    tooltip="Restaurant",
                    icon=folium.Icon(color="blue", icon="cutlery", prefix="fa"),
                ).add_to(m)

            for o in orders:
                lat, lng = o.get("latitude"), o.get("longitude")
                if lat is None or lng is None:
                    continue
                cust_c = [float(lat), float(lng)]
                colour, icon = _pin(o.get("order_status", "Pending"))
                total_e = o.get("total_eta")

                folium.Marker(
                    location=cust_c,
                    popup=folium.Popup(_popup_html(o), max_width=270),
                    tooltip=(
                        f"{o['order_id']} | ETA: {total_e:.0f} min"
                        if total_e is not None else o["order_id"]
                    ),
                    icon=folium.Icon(color=colour, icon=icon, prefix="fa"),
                ).add_to(m)

                if st.session_state.rest_address:
                    # Cache polyline per order to avoid a live API call on every
                    # 10-second autorefresh — same pattern as dist_preview.
                    _order_id = o["order_id"]
                    poly_key = f"polyline_{_order_id}"
                    if poly_key not in st.session_state:
                        try:
                            _pd = get_directions_data(rest_c, cust_c)
                            st.session_state[poly_key] = _pd["polyline_pts"]
                        except Exception as _poly_err:
                            # Log so the failure is visible, not silently swallowed
                            st.session_state[poly_key] = None
                            st.warning(f"Route line unavailable for {_order_id}: {_poly_err}")

                    if st.session_state.get(poly_key):
                        folium.PolyLine(
                            locations=st.session_state[poly_key],
                            color="#667eea", weight=4,
                            tooltip=f"Road route to {_order_id}",
                        ).add_to(m)
                    else:
                        # Fallback straight line when API unavailable
                        folium.PolyLine(
                            locations=[rest_c, cust_c],
                            color="#f59e0b", weight=3, dash_array="6 4",
                            tooltip=f"Straight-line estimate to {_order_id}",
                        ).add_to(m)

            st_folium(m, width=700, height=500, returned_objects=[])
            if not orders and db_ok:
                st.info("No active orders on the map.")

    # ── Order cards + Predict button ──────────
    with col_cards:
        st.markdown("#### Orders")
        st.caption(
            "Predict button appears once the Chef has confirmed prep time. "
            "Set the restaurant address in the sidebar first."
        )

        if not orders:
            st.info("No active orders." if db_ok else "DB unavailable.")
        else:
            _CSS = {
                "Pending":   "#f59e0b",
                "Preparing": "#3b82f6",
                "Ready":     "#22c55e",
                "Delivered": "#6b7280",
            }

            for o in orders:
                oid     = o["order_id"]
                status  = o.get("order_status", "Pending")
                prep    = o.get("confirmed_prep_time")
                eta_val = o.get("total_eta")
                lat     = o.get("latitude")
                lng     = o.get("longitude")
                ri      = int(o.get("ready_items") or 0)
                ti      = int(o.get("total_items") or 0)
                rtype   = o.get("restaurant_type", "Fast Food")

                with st.container(border=True):
                    h1, h2 = st.columns([3, 1])
                    h1.markdown(f"**{oid}**")
                    h2.markdown(
                        f"<span style='color:{_CSS.get(status, '#ef4444')};"
                        f"font-weight:700'>{status}</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"Address: {o.get('customer_address', '-')}")

                    m1, m2 = st.columns(2)
                    m1.metric("Prep", f"{prep:.0f} min" if prep is not None else "-")
                    m2.metric("ETA",  f"{eta_val:.0f} min" if eta_val is not None else "Pending")

                    if ti:
                        st.progress(ri / ti, text=f"{ri}/{ti} items ready")

                    # ── Predict button — only after Chef confirms prep time ────
                    if prep is not None and lat is not None:
                        rest_c   = st.session_state.rest_coords
                        cust_c   = [float(lat), float(lng)]

                        # Cache distance preview to avoid API call on every refresh
                        preview_key = f"dist_preview_{oid}"
                        if preview_key not in st.session_state:
                            try:
                                _prev = get_directions_data(rest_c, cust_c)
                                st.session_state[preview_key] = _prev["distance_km"]
                            except Exception as _e:
                                st.session_state[preview_key] = None
                                st.error(f"Google API Error (distance preview): {_e}")

                        if st.session_state.get(preview_key) is not None:
                            st.markdown(
                                f"<p style='color:#4f8ef7; font-weight:600; "
                                f"background:transparent;'>"
                                f"📍 <code style='background:#2d3348; color:#4f8ef7; "
                                f"padding:2px 6px; border-radius:4px;'>"
                                f"{st.session_state[preview_key]:.3f} km</code> "
                                f"<span style='color:#9ca3af; font-size:0.85rem;'>"
                                f"Google Directions API</span></p>",
                                unsafe_allow_html=True,
                            )

                        if st.button(
                            "Predict Delivery ETA",
                            key=f"pred_{oid}",
                            use_container_width=True,
                        ):
                            result_area = st.container()

                            with st.spinner("Calling ETA API..."):
                                try:
                                    # Step 1: Google Directions API
                                    dir_data         = get_directions_data(rest_c, cust_c)
                                    dist_km          = dir_data["distance_km"]
                                    traffic_level    = dir_data["traffic_level"]
                                    duration_traffic = dir_data["duration_traffic"]
                                    traffic_ratio    = dir_data["traffic_ratio"]
                                    st.session_state[preview_key] = dist_km

                                    st.write(
                                        f"📍 `{dist_km:.3f} km` | "
                                        f"🚦 traffic: **{traffic_level.upper()}** "
                                        f"(ratio {traffic_ratio:.2f}x) | "
                                        f"⏱️ Google travel: **{duration_traffic:.1f} min**"
                                    )

                                    # Step 2: Build payload for hybrid ETA API
                                    payload = {
                                        "order_id":            oid,
                                        "origin_lat":          float(rest_c[0]),
                                        "origin_lng":          float(rest_c[1]),
                                        "dest_lat":            float(lat),
                                        "dest_lng":            float(lng),
                                        "distance_km":         float(dist_km),
                                        "google_duration_min": float(duration_traffic),
                                        "restaurant_type":     normalize_restaurant_type(rtype),
                                        "order_items":         max(ti, 1),
                                        "traffic_level":       traffic_level,
                                        "weather":             "clear",
                                        "rider_rating":        4.5,
                                        "vehicle_type":        "motorcycle",
                                        "city":                "Cairo",
                                        "driver_age":          29,
                                    }

                                    with st.expander("📦 Payload sent to ETA API", expanded=False):
                                        st.json(payload)

                                    # Step 3: Call ETA API
                                    api_result = call_eta_api(payload)

                                    with st.expander("🔎 Raw API response", expanded=False):
                                        st.json(api_result)

                                except RuntimeError as api_err:
                                    st.error(str(api_err))
                                    st.stop()
                                except Exception as exc:
                                    st.error(f"Prediction failed: {exc}")
                                    st.stop()

                            # ── Hybrid ETA breakdown ──────────────────────────
                            with result_area:
                                c1, c2, c3, c4, c5 = st.columns(5)
                                c1.metric("🍳 Kitchen Prep",
                                          f"{api_result['prep_time_min']:.1f} min")
                                c2.metric("🗺️ Google Travel",
                                          f"{api_result['google_travel_time']:.1f} min")
                                c3.metric("📐 Base ETA",
                                          f"{api_result['base_eta']:.1f} min",
                                          help="prep + Google travel")
                                c4.metric("🧠 ML Correction",
                                          f"{api_result['ml_adjustment']:.1f} min",
                                          help="clamped ±10 min")
                                c5.metric("🚚 Final ETA",
                                          f"{api_result['total_eta_min']:.1f} min",
                                          delta=f"{api_result['distance_km']:.1f} km")
                                st.success(
                                    f"**{oid}** — Final ETA: **{api_result['total_eta_min']:.1f} min**  \n"
                                    f"Base (Google + prep): {api_result['base_eta']:.1f} min  |  "
                                    f"ML raw: {api_result['ml_eta_raw']:.1f} min  |  "
                                    f"Correction: {api_result['ml_adjustment']:+.1f} min"
                                )

                                # ── DSS Recommendation ────────────────────────
                                current_hour  = datetime.now().hour
                                is_peak       = current_hour in range(17, 21)
                                is_long       = dist_km > 10
                                _pt           = api_result.get("prep_time_min")
                                is_high_prep  = _pt > 20 if _pt is not None else False

                                if traffic_level == "high" and is_peak:
                                    st.warning("🚨 **DSS Alert:** High traffic during peak hours — "
                                               "assign your most experienced rider immediately.")
                                elif traffic_level == "high":
                                    st.warning("⚠️ **DSS Alert:** High traffic detected — "
                                               "consider assigning an experienced rider.")
                                elif is_peak and is_long:
                                    st.warning("⚠️ **DSS Alert:** Peak hours with long distance — "
                                               "add extra rider to avoid delay.")
                                elif is_peak:
                                    st.info("📊 **DSS Note:** Peak hours (17-20) detected — "
                                            "expect slightly higher delivery times.")
                                elif traffic_level == "medium" and is_long:
                                    st.info("📊 **DSS Note:** Medium traffic on long route — "
                                            "monitor this order closely.")
                                elif is_high_prep:
                                    st.info("📊 **DSS Note:** High preparation time detected — "
                                            "notify customer of extended wait.")
                                else:
                                    st.success("✅ **DSS:** Low traffic, standard conditions — "
                                               "normal rider assignment recommended.")

                    elif prep is None:
                        st.caption("Waiting for Chef to confirm prep time.")

                    # ── Mark as Delivered — only for Ready orders ─────────────
                    if status == "Ready":
                        if st.button(
                            "✅ Mark as Delivered",
                            key=f"deliver_{oid}",
                            use_container_width=True,
                            type="primary",
                        ):
                            try:
                                import psycopg2
                                conn = psycopg2.connect(
                                    host="localhost", port=5555,
                                    database="food_delivery",
                                    user="root", password="root"
                                )
                                with conn.cursor() as cur:
                                    cur.execute(
                                        "UPDATE orders SET status = 'Delivered' "
                                        "WHERE order_id = %s",
                                        (oid,)
                                    )
                                conn.commit()
                                conn.close()
                                st.toast(f"✅ Order {oid} marked as Delivered!", icon="✅")
                                # Clear cached data to refresh
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to mark delivered: {e}")

# =============================================================================
# TAB 3 - DSS Insights
# =============================================================================
with tab_dss:
    st_autorefresh(interval=60_000, key="dss_refresh")

    # ── SECTION 1: Late Order Alerts ──────────────────────────────────────────
    st.markdown("<div class='section-header'>🚨 Late Order Alerts</div>", unsafe_allow_html=True)
    try:
        with get_engine().connect() as _conn:
            late_orders = _conn.execute(text("""
                SELECT
                    order_id,
                    restaurant_type,
                    total_eta,
                    round((EXTRACT(EPOCH FROM (NOW() - created_at)) / 60)::numeric, 1)
                        AS elapsed_min,
                    round(((EXTRACT(EPOCH FROM (NOW() - created_at)) / 60)
                        - total_eta)::numeric, 1) AS overdue_min
                FROM orders
                WHERE status IN ('Preparing', 'Pending')
                  AND total_eta IS NOT NULL
                  AND created_at > NOW() - INTERVAL '3 hours'
                  AND EXTRACT(EPOCH FROM (NOW() - created_at)) / 60 > total_eta
                ORDER BY overdue_min DESC
            """)).mappings().all()

        if not late_orders:
            st.success("✅ All orders are on time.")
        else:
            st.error(f"⚠️ {len(late_orders)} order(s) running late!")
            for order in late_orders:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Order",        order["order_id"])
                    c2.metric("Expected ETA", f"{order['total_eta']:.0f} min")
                    c3.metric("Overdue",      f"{order['overdue_min']:.0f} min",
                              delta=f"{order['overdue_min']:.0f} min late",
                              delta_color="inverse")
    except Exception as _e:
        st.error(f"Late order query failed: {_e}")

    st.markdown("---")

    # ── SECTION 2: Kitchen Bottleneck Detection ───────────────────────────────
    st.markdown("<div class='section-header'>🍳 Kitchen Bottleneck Detection</div>", unsafe_allow_html=True)
    try:
        _db      = get_db()
        workload = _db.get_station_workload()
        staffing = _db.get_staffing()

        if not workload:
            st.info("No active kitchen workload.")
        else:
            staffing_dict = {s["station_name"]: s["chef_count"] for s in staffing}
            rows = []
            for station, load in workload.items():
                chefs         = staffing_dict.get(station, 1)
                load_per_chef = load / chefs if chefs > 0 else load
                rows.append({
                    "Station":              station.replace("_", " ").title(),
                    "Total Workload (min)": round(load, 1),
                    "Chefs":               chefs,
                    "Load per Chef":       round(load_per_chef, 1),
                    "Status": (
                        "🔴 Overloaded" if load_per_chef > 20
                        else "🟡 Busy"  if load_per_chef > 10
                        else "🟢 Normal"
                    ),
                })
            df_workload = pd.DataFrame(rows).sort_values("Load per Chef", ascending=False)
            st.dataframe(df_workload, use_container_width=True)

            overloaded = [r for r in rows if "Overloaded" in r["Status"]]
            if overloaded:
                st.warning(
                    f"⚠️ Recommendation: Add more staff to "
                    f"{', '.join([r['Station'] for r in overloaded])}"
                )
            else:
                st.success("✅ Kitchen workload is balanced.")
    except Exception as _e:
        st.error(f"Kitchen workload query failed: {_e}")

    st.markdown("---")

    # ── SECTION 3: Best Hour to Order Analytics ───────────────────────────────
    st.markdown("<div class='section-header'>⏰ Best Hours to Order</div>", unsafe_allow_html=True)
    try:
        df_hours    = pd.DataFrame(_get_hour_stats())
        df_hours["avg_delivery"] = pd.to_numeric(df_hours["avg_delivery"], errors="coerce")
        df_hours["hour_of_day"]  = pd.to_numeric(df_hours["hour_of_day"],  errors="coerce")
        df_hours    = df_hours.dropna(subset=["avg_delivery"])
        best_hours  = df_hours.nsmallest(3, "avg_delivery")
        worst_hours = df_hours.nlargest(3, "avg_delivery")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🟢 Fastest delivery hours:**")
            for _, row in best_hours.iterrows():
                st.write(f"  {int(row['hour_of_day']):02d}:00 → avg {row['avg_delivery']} min")
        with c2:
            st.markdown("**🔴 Slowest delivery hours:**")
            for _, row in worst_hours.iterrows():
                st.write(f"  {int(row['hour_of_day']):02d}:00 → avg {row['avg_delivery']} min")

        st.bar_chart(
            df_hours.set_index("hour_of_day")["avg_delivery"],
            use_container_width=True,
        )

        current_hour = datetime.now().hour
        current_avg  = df_hours[df_hours["hour_of_day"] == current_hour]["avg_delivery"].values
        if len(current_avg) > 0:
            st.info(
                f"📍 Current hour ({current_hour:02d}:00): "
                f"avg delivery = {current_avg[0]} min"
            )
    except Exception as _e:
        st.error(f"Hour analytics query failed: {_e}")

    st.markdown("---")

    # ── SECTION 4: Restaurant Type Recommendation ─────────────────────────────
    st.markdown("<div class='section-header'>🍽️ Restaurant Type Performance</div>", unsafe_allow_html=True)
    try:
        rest_perf = _get_restaurant_perf()
        df_rest   = pd.DataFrame(rest_perf)
        for col in ["avg_delivery", "avg_prep", "avg_total"]:
            if col in df_rest.columns:
                df_rest[col] = pd.to_numeric(df_rest[col], errors="coerce")
        st.dataframe(df_rest, use_container_width=True)

        if len(df_rest) > 0:
            best  = df_rest.iloc[0]
            worst = df_rest.iloc[-1]
            st.success(
                f"✅ **Recommendation:** "
                f"{best['restaurant_type'].replace('_', ' ').title()} "
                f"has the fastest total time ({best['avg_total']} min avg). "
                f"Prioritize these orders during peak hours."
            )
            st.warning(
                f"⚠️ **Note:** "
                f"{worst['restaurant_type'].replace('_', ' ').title()} "
                f"takes the longest ({worst['avg_total']} min avg). "
                f"Assign experienced riders to these orders."
            )

        st.markdown("#### Kitchen Prep Time by Restaurant Type")
        df_dim = pd.DataFrame(_get_dim_restaurants())
        if not df_dim.empty:
            st.bar_chart(
                df_dim.set_index("restaurant_type")["avg_prep_time_min"],
                use_container_width=True,
            )
    except Exception as _e:
        st.error(f"Restaurant performance query failed: {_e}")
