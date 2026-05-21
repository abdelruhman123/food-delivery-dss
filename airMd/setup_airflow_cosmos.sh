#!/bin/bash

# Professional Airflow + Cosmos Setup
# Airflow 2.10.5 with Astronomer Cosmos for dbt integration

echo "=========================================="
echo "  Airflow 2.10.5 + Cosmos Setup"
echo "=========================================="
echo ""

# Set base path
BASE_PATH="/mnt/d/Food Delivery Dss"
VENV_PATH="$BASE_PATH/venv"

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

if [ $? -ne 0 ]; then
    echo "❌ Failed to activate venv. Creating new one..."
    python3 -m venv "$VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

echo "✓ Virtual environment activated"

# Set Airflow home
export AIRFLOW_HOME=~/airflow
echo "📁 Airflow home: $AIRFLOW_HOME"

# Upgrade pip
echo ""
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install Airflow 2.10.5 with constraints
echo ""
echo "📦 Installing Apache Airflow 2.10.5..."
AIRFLOW_VERSION=2.10.5
PYTHON_VERSION="$(python3 --version | cut -d " " -f 2 | cut -d "." -f 1-2)"
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"

# Install Postgres provider
echo ""
echo "📦 Installing Postgres provider..."
pip install apache-airflow-providers-postgres

# Install Astronomer Cosmos
echo ""
echo "📦 Installing Astronomer Cosmos..."
pip install "astronomer-cosmos[dbt-postgres]"

# Install other required packages
echo ""
echo "📦 Installing additional dependencies..."
pip install pandas numpy scikit-learn xgboost joblib sqlalchemy psycopg2-binary

# Initialize Airflow database
echo ""
echo "🗄️  Initializing Airflow database..."
airflow db init

# Create admin user
echo ""
echo "👤 Creating admin user..."
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@delivery-dss.com \
    --password admin123

# Create necessary directories
echo ""
echo "📁 Creating directory structure..."
mkdir -p $AIRFLOW_HOME/dags
mkdir -p $AIRFLOW_HOME/logs
mkdir -p $AIRFLOW_HOME/plugins
mkdir -p $BASE_PATH/logs

# Configure Airflow
echo ""
echo "⚙️  Configuring Airflow..."

# Update airflow.cfg
sed -i "s|dags_folder = .*|dags_folder = $AIRFLOW_HOME/dags|g" $AIRFLOW_HOME/airflow.cfg
sed -i 's/load_examples = True/load_examples = False/g' $AIRFLOW_HOME/airflow.cfg
sed -i 's/dag_dir_list_interval = 300/dag_dir_list_interval = 30/g' $AIRFLOW_HOME/airflow.cfg

# Copy DAG files
echo ""
echo "📋 Copying DAG files..."
cp "$BASE_PATH/Dss/airflow/dags/delivery_dss_cosmos_dag.py" $AIRFLOW_HOME/dags/ 2>/dev/null || echo "  (DAG file will be created)"

# Create Airflow connection for Postgres
echo ""
echo "🔗 Creating Postgres connection..."
airflow connections add 'postgres_delivery' \
    --conn-type 'postgres' \
    --conn-host 'localhost' \
    --conn-login 'your_username' \
    --conn-password 'your_password' \
    --conn-port 5432 \
    --conn-schema 'your_database' 2>/dev/null || echo "  (Connection may already exist)"

# Set Airflow variables
echo ""
echo "📝 Setting Airflow variables..."
airflow variables set BASE_PATH "$BASE_PATH"
airflow variables set DBT_PROJECT_PATH "$BASE_PATH/delivery_transform"
airflow variables set VENV_PYTHON "$VENV_PATH/bin/python3"

# Verify installation
echo ""
echo "✅ Verifying installation..."
echo "Airflow version: $(airflow version)"
echo "Python version: $(python3 --version)"
echo "Cosmos installed: $(pip show astronomer-cosmos | grep Version)"

echo ""
echo "=========================================="
echo "  ✅ Setup Complete!"
echo "=========================================="
echo ""
echo "📋 Summary:"
echo "  - Airflow 2.10.5 installed"
echo "  - Astronomer Cosmos configured"
echo "  - Postgres provider ready"
echo "  - Admin user created (admin/admin123)"
echo ""
echo "🚀 Next steps:"
echo ""
echo "1. Start Airflow webserver (Terminal 1):"
echo "   source $VENV_PATH/bin/activate"
echo "   airflow webserver --port 8080"
echo ""
echo "2. Start Airflow scheduler (Terminal 2):"
echo "   source $VENV_PATH/bin/activate"
echo "   airflow scheduler"
echo ""
echo "3. Access Airflow UI:"
echo "   http://localhost:8080"
echo "   Username: admin"
echo "   Password: admin123"
echo ""
echo "=========================================="
