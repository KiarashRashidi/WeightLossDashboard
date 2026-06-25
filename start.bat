@echo off
echo ============================================
echo  SmartWeigh MedDash - Starting
echo ============================================
echo.

:: --- Start Flask backend in a new window ---
echo Starting Flask backend on http://localhost:5000 ...
start "SmartWeigh Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate && python app.py"

:: Wait a moment for the backend to initialize
timeout /t 3 /nobreak >nul

:: --- Start React frontend in a new window ---
echo Starting React frontend on http://localhost:3000 ...
start "SmartWeigh Frontend" cmd /k "cd /d "%~dp0frontend" && npm start"

echo.
echo Both servers are starting in separate windows.
echo.
echo  Backend:  http://localhost:5000
echo  Frontend: http://localhost:3000  (opens in browser automatically)
echo.
echo Default credentials:  doctor / changeme123
echo (Change in backend\.env before going live)
echo.
pause
