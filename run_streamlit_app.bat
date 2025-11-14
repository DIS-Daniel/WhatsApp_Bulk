@echo off
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please install Python from https://www.python.org/downloads/
    pause
    exit /b
)
python -m streamlit --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Streamlit is not installed. Installing now...
    pip install streamlit
)
streamlit run Streamlit.py
pause
