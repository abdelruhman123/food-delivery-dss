# Streamlit Apps — Food Delivery DSS

Three Streamlit applications serving different user roles.
All prediction logic is delegated to FastAPI (port 8000).

## How to Run

```bash
# Start FastAPI first
uvicorn eta_api:app --reload --port 8000

# Then start all three apps
streamlit run Dss/customer_app.py  --server.port 8501
streamlit run Dss/kitchen_app.py   --server.port 8502
streamlit run streamlit_app.py     --server.port 8503
```

---

## App 1 — Customer App (port 8501)

**File:** `Dss/customer_app.py`

### Responsibilities
- Browse menu and build cart
- Enter delivery address (geocoded via Google Maps)
- Place order → saved to PostgreSQL
- Poll DB every 10s → show Total ETA once Manager predicts

### Flow
```
Customer enters address → geocoded to lat/lng
Customer selects items → cart built
Customer places order → saved to public.orders + public.live_orders
Kitchen confirms prep → order status: Preparing
Manager predicts ETA → total_eta written to DB
Customer sees ETA → auto-refreshes every 10s
```

---

## App 2 — Kitchen App (port 8502)

**File:** `Dss/kitchen_app.py`

### Responsibilities
- Sidebar: manage chef headcount per station
- Section 1: incoming orders awaiting chef confirmation
  - Shows system-suggested prep time
  - Chef adjusts and confirms → saved to `orders.confirmed_prep_time`
  - Status updated to `Preparing`
- Section 2: live item tracking with "Mark Ready" buttons
  - When all items ready → order status → `Ready`

### Key Logic
- Chef's confirmed prep time is used by FastAPI (not recalculated)
- Station workload drives kitchen bottleneck detection in DSS

---

## App 3 — Manager DSS (port 8503)

**File:** `streamlit_app.py`

### Tabs

#### Tab 1 — Dashboard & Model Info
- KPI cards: Total Orders, Avg Delivery, Fastest, Slowest
- Bar chart: Avg delivery time by traffic level
- Recent 20 orders table (colored by status)
- Model info: status, feature count, contract version

**Data source:** `GET /dashboard-kpis` → `dbt_schema_marts.fct_orders`

#### Tab 2 — Live Orders Map
- OpenStreetMap with order pins (color by status)
- Order cards with Prep + ETA metrics
- "Predict Delivery ETA" button per order:
  1. Calls Google Maps Directions API → distance + traffic
  2. Posts to `POST /predict-eta`
  3. Shows 5-metric breakdown: Prep | Google Travel | Base ETA | ML Correction | Final ETA
  4. DSS recommendation message based on traffic + distance + time
  5. "Mark as Delivered" button for Ready orders

**Data source:** `db_manager.get_manager_map_data()`

#### Tab 3 — DSS Insights
Four decision-support sections:

1. **Late Order Alerts** — orders exceeding ETA in last 3 hours
2. **Kitchen Bottleneck Detection** — workload per chef per station
3. **Best Hours to Order** — avg delivery time by hour of day
4. **Restaurant Type Performance** — avg total time by restaurant type

**Data sources:**
- `public.orders` (live)
- `public.kitchen_staffing` + `station_metrics` view
- `dbt_schema_marts.fct_orders` (historical)
- `public.dim_restaurants`

---

## Architecture Rules

```
✅ All ML predictions → FastAPI /predict-eta
✅ All analytics → dbt_schema_marts.fct_orders (clean pipeline)
✅ All live operations → public.orders, public.live_orders
✅ Google Maps → manager app only (distance + traffic)
✅ Chef prep time → fetched from DB, not recalculated
✅ No model artifacts loaded in Streamlit
```

---

## ETA Formula

```
google_travel  = Google Maps duration_in_traffic
confirmed_prep = chef's confirmed value from DB
ml_raw         = model.predict(24 features)

travel_time    = 0.6 × google_travel + 0.4 × ml_raw
total_eta      = travel_time + confirmed_prep
```

---

## Performance

- Dashboard KPIs cached 30s (`@st.cache_data`)
- Hour/restaurant analytics cached 60s
- DB orders cached 15s
- Google Maps polylines cached per order (session state)
- Autorefresh: map tab 30s, DSS tab 60s
