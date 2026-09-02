@echo off
echo ============================================================
echo  Loan Knowledge Assistance - Frontend
echo ============================================================
echo.

cd /d "%~dp0frontend"

echo Checking Node.js...
node --version
if errorlevel 1 (
    echo ERROR: Node.js not found. Install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

echo.
echo Installing npm dependencies...
npm install

echo.
echo Starting Vite dev server on http://localhost:5173
echo.

npm run dev

pause
