@echo off
echo ============================================
echo  SmartWeigh MedDash - Setup
echo ============================================

:: --- Backend setup ---
echo.
echo [1/3] Setting up Python backend...
cd /d "%~dp0backend"

if not exist ".env" (
    copy ".env.example" ".env"
    echo   Created .env from template. Edit it to add your API keys.
) else (
    echo   .env already exists.
)

python -m venv venv 2>nul
if errorlevel 1 (
    echo   ERROR: Python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

call venv\Scripts\activate
pip install -r requirements.txt --quiet
echo   Backend dependencies installed.

:: --- Frontend setup ---
echo.
echo [2/3] Setting up React frontend...
cd /d "%~dp0frontend"

where node >nul 2>nul
if errorlevel 1 (
    echo   ERROR: Node.js not found. Please install Node.js 18+ from nodejs.org.
    pause
    exit /b 1
)

npm install --silent
echo   Frontend dependencies installed.

echo.
echo [3/3] Setup complete!
echo.
echo Next steps:
echo   1. Edit backend\.env with your GAPGPT_API_KEY and BALE_BOT_TOKEN
echo   2. Run start.bat to launch the application
echo.
pause
