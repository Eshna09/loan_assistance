@echo off
echo ============================================================
echo  Loan Knowledge Assistance - Backend
echo ============================================================
echo.

cd /d "%~dp0backend"

echo Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting FastAPI backend on http://localhost:8000
echo API docs: http://localhost:8000/docs
echo.
echo IMPORTANT: Make sure Ollama is running separately:
echo   1. Install Ollama from https://ollama.com
echo   2. Run: ollama serve
echo   3. Run: ollama pull codellama:7b
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
