# 🚚 Food Delivery Decision Support System

> A production-grade data engineering and ML platform for food delivery operations — built as a TM471 Final Year Project at Arab Open University.

[![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)](https://python.org)
[![dbt](https://img.shields.io/badge/dbt-1.8.7-orange?logo=dbt)](https://getdbt.com)
[![Airflow](https://img.shields.io/badge/Airflow-2.10.5-017CEE?logo=apache-airflow)](https://airflow.apache.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32-FF4B4B?logo=streamlit)](https://streamlit.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql)](https://postgresql.org)

---

## 📋 Overview

The **Food Delivery DSS** is a complete data engineering pipeline and decision-support platform that transforms 45,593 raw delivery records into actionable operational insights for internal staff.

The system combines:
- A **3-layer dbt ELT pipeline** with automated quality validation
- A **RandomForest ML model** for delivery time prediction
- A **hybrid ETA formula** integrating Google Maps real-time traffic
- **Apache Airflow** orchestration with daily automated retraining
- **3 role-specific Streamlit applications** for customers, kitchen staff, and managers

---

## 📸 Screenshots

### System Architecture
![System Architecture](screenshots/architecture.jpg)

### Manager DSS — Live Orders Map
![Manager DSS](screenshots/manager_dss.jpg)

### Airflow DAG — All Tasks Successful
![Airflow DAG](screenshots/airflow_dag.jpg)

---

## 🏗️ System Architecture

```
Raw Data (CSV)
      ↓
PostgreSQL (Docker)
      ↓
Apache Airflow + Astronomer Cosmos
      ↓
dbt ELT Pipeline (Staging → Core → Marts)
      ↓
RandomForest ML Model
      ↓
FastAPI + Google Maps API
      ↓
┌──────────────────────────────────────────┐
│  Customer App  │  Kitchen App  │  Manager DSS  │
│   Port 8501    │   Port 8502   │   Port 8503   │
└──────────────────────────────────────────┘
```

---

## 🔧 Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Database | PostgreSQL 15 (Docker) | Raw + operational data storage |
| Data Pipeline | dbt Core 1.8.7 | ELT transformation + quality testing |
| Orchestration | Apache Airflow 2.10.5 + Cosmos 1.13.1 | Daily pipeline automation |
| ML Framework | RandomForest + XGBoost | Model training and evaluation |
| API Layer | FastAPI + Uvicorn | ML inference endpoint |
| Maps | Google Maps Platform | Real-time travel time + geocoding |
| Frontend | Streamlit 1.32 | 3 role-specific interfaces |

---

## 📊 Pipeline Results

| Metric | Value |
|---|---|
| Raw Records | 45,593 |
| Clean Records (after 3-layer validation) | 41,507 (91%) |
| dbt Tests | 12/12 Passing |
| Production Model MAE | 4.68 min |
| Pipeline Schedule | Daily at 02:00 AM |

---

## 🗂️ Project Structure

```
food-delivery-dss/
│
├── delivery_transform/          # dbt project
│   └── models/
│       ├── staging/             # stg_orders
│       ├── core/                # dim_driver, dim_restaurant, fact_orders
│       └── marts/               # fct_orders, ml_training_dataset
│
├── Dss/
│   ├── customer_app.py          # Streamlit Customer App (port 8501)
│   ├── kitchen_app.py           # Streamlit Kitchen App (port 8502)
│   ├── db_manager.py            # Database operations
│   └── airflow/dags/            # Airflow DAG
│
├── screenshots/                 # Project screenshots
├── eta_api.py                   # FastAPI prediction service
├── ml_models_enhanced.py        # Production ML training
├── ml_models_new_ml.py          # Experimental ML training
├── streamlit_app.py             # Manager DSS (port 8503)
├── feature_contract.py          # ML feature validation
└── ingest_data.py               # Raw data ingestion
```

---

## 🚀 Getting Started

### Prerequisites
- Docker Desktop
- Python 3.10+
- Google Maps API Key

### 1. Start PostgreSQL
```bash
docker run -d \
  --name pg_delivery \
  -e POSTGRES_USER=root \
  -e POSTGRES_PASSWORD=root \
  -e POSTGRES_DB=food_delivery \
  -p 5555:5432 \
  postgres:15
```

### 2. Install Dependencies
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements/requirements.txt
```

### 3. Add Google Maps API Key
In `streamlit_app.py` and `Dss/customer_app.py`, replace:
```python
GOOGLE_MAPS_KEY = "YOUR_GOOGLE_MAPS_API_KEY"
```

### 4. Load Data
```bash
python ingest_data.py
```

### 5. Run dbt Pipeline
```bash
cd delivery_transform
dbt run
dbt test
cd ..
```

### 6. Train ML Models
```bash
python ml_models_enhanced.py
```

### 7. Start the System
```bash
# Terminal 1 — API
uvicorn eta_api:app --reload --port 8000

# Terminal 2 — Customer App
streamlit run Dss/customer_app.py --server.port 8501

# Terminal 3 — Kitchen App
streamlit run Dss/kitchen_app.py --server.port 8502

# Terminal 4 — Manager DSS
streamlit run streamlit_app.py --server.port 8503
```

---

## 🔄 Airflow Pipeline

The Airflow DAG `delivery_dss_pipeline` runs daily at 02:00 AM:

```
dbt_clean_pipeline  ──► train_baseline_model ──┐
                                                ├──► validate_pipeline ──► pipeline_summary
dbt_new_ml_pipeline ──► train_new_ml_model  ───┘
```

```bash
airflow webserver --port 8080
airflow scheduler
```

---

## 📱 Applications

### Customer App (Port 8501)
- Browse menu and place orders
- Address geocoding via Google Maps
- Real-time ETA tracking

### Kitchen App (Port 8502)
- View incoming orders
- Confirm real preparation time
- Mark items as ready

### Manager DSS (Port 8503)
- **Dashboard Tab:** Live KPIs, traffic chart, recent orders
- **Live Orders Map Tab:** Cairo map with order pins, ETA prediction, DSS recommendations
- **DSS Insights Tab:** Late order alerts, kitchen bottleneck detection, best hours analytics

---

## 🤖 ML Model

**ETA Hybrid Formula:**
```python
travel_time = 0.6 × google_maps_duration + 0.4 × ml_prediction
total_eta   = travel_time + chef_confirmed_prep_time
```

**Features:** 17 numerical + 7 categorical = 24 total features

**Model Selection:**
The production model was selected based on data quality reliability — trained exclusively on 40,182 quality-validated records. An experimental model trained on the full dataset is available via `MODEL_VARIANT=new_ml`.

---

## 📄 Data Quality — 3-Layer Validation

| Layer | Condition | Records Removed |
|---|---|---|
| Layer 1 | Corrupted GPS coordinates (lat=0 or lon=0) | 3,640 |
| Layer 2 | Invalid delivery time (≤0 or >240 min) | ~200 |
| Layer 3 | Impossible speed (>120 km/h) | ~246 |
| **Total** | **Clean records retained** | **41,507 (91%)** |

---

## 👤 Author

**Abdelrahman Ahmed Emam**

---

screenshots/architecture.jpg    
screenshots/manager_dss.jpg     
screenshots/airflow_dag.jpg     