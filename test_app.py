"""
Test script to verify Streamlit app setup.
Checks all required packages before launching.

Usage:
    python test_app.py
"""

import sys
import os

def test_dependencies():
    """Test if all required packages are installed"""
    print("="*80)
    print("TESTING DEPENDENCIES")
    print("="*80)
    
    required_packages = [
        'streamlit',
        'pandas',
        'numpy',
        'joblib',
        'plotly',
        'folium',
        'streamlit_folium',
        'sklearn',
        'xgboost',
        'sqlalchemy'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package:20s} - Installed")
        except ImportError:
            print(f"❌ {package:20s} - Missing")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install -r requirements_streamlit.txt")
        return False
    else:
        print("\n✅ All dependencies installed!")
        return True

def test_model_files():
    """Test if model files exist"""
    print("\n" + "="*80)
    print("TESTING MODEL FILES")
    print("="*80)
    
    model_files = [
        'eta_model.joblib',
        'demand_model.joblib',
        'preprocessor.joblib'
    ]
    
    missing_files = []
    
    for file in model_files:
        if os.path.exists(file):
            size = os.path.getsize(file) / (1024 * 1024)  # Size in MB
            print(f"✅ {file:25s} - Found ({size:.2f} MB)")
        else:
            print(f"❌ {file:25s} - Not found")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n⚠️  Missing model files: {', '.join(missing_files)}")
        print("Train models with: python save_models_for_streamlit.py")
        return False
    else:
        print("\n✅ All model files present!")
        return True

def test_streamlit_app():
    """Test if streamlit app file exists and is valid"""
    print("\n" + "="*80)
    print("TESTING STREAMLIT APP")
    print("="*80)
    
    if not os.path.exists('streamlit_app.py'):
        print("❌ streamlit_app.py not found")
        return False
    
    print("✅ streamlit_app.py found")
    
    # Check file size
    size = os.path.getsize('streamlit_app.py') / 1024  # Size in KB
    print(f"   File size: {size:.2f} KB")
    
    # Check if it's a valid Python file
    try:
        with open('streamlit_app.py', 'r') as f:
            content = f.read()
            if 'import streamlit' in content:
                print("✅ Valid Streamlit app")
                return True
            else:
                print("❌ Not a valid Streamlit app")
                return False
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

def test_config_files():
    """Test if configuration files exist"""
    print("\n" + "="*80)
    print("TESTING CONFIGURATION FILES")
    print("="*80)
    
    config_files = [
        'requirements_streamlit.txt',
        '.streamlit/config.toml',
        'STREAMLIT_README.md',
        'QUICKSTART.md'
    ]
    
    for file in config_files:
        if os.path.exists(file):
            print(f"✅ {file:35s} - Found")
        else:
            print(f"⚠️  {file:35s} - Not found (optional)")
    
    return True

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("DELIVERY DSS - PRE-LAUNCH VERIFICATION")
    print("="*80 + "\n")
    
    results = []
    
    # Test 1: Dependencies
    results.append(("Dependencies", test_dependencies()))
    
    # Test 2: Model Files
    results.append(("Model Files", test_model_files()))
    
    # Test 3: Streamlit App
    results.append(("Streamlit App", test_streamlit_app()))
    
    # Test 4: Config Files
    results.append(("Config Files", test_config_files()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20s} - {status}")
        if not result:
            all_passed = False
    
    print("="*80)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYou can now launch the app:")
        print("   streamlit run streamlit_app.py")
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("\nPlease fix the issues above before launching the app.")
        print("\nQuick fixes:")
        print("   1. Install dependencies: pip install -r requirements_streamlit.txt")
        print("   2. Train models: python save_models_for_streamlit.py")
    
    print("="*80 + "\n")
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
