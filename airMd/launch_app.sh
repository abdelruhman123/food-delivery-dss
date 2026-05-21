#!/bin/bash

# Delivery DSS - Launch Script
# This script checks prerequisites and launches the Streamlit app

echo "=========================================="
echo "  Delivery DSS - Launch Script"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed"
    exit 1
fi

echo "✅ pip3 found"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo ""
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -q -r requirements_streamlit.txt

# Run tests
echo ""
echo "🧪 Running pre-launch tests..."
python test_app.py

# Check test results
if [ $? -eq 0 ]; then
    echo ""
    echo "🚀 Launching Streamlit app..."
    echo ""
    streamlit run streamlit_app.py
else
    echo ""
    echo "❌ Pre-launch tests failed"
    echo "Please fix the issues and try again"
    exit 1
fi
