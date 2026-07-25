@echo off
setlocal
cd /d "%~dp0"

if not defined CAMPUS_DATA_DIR set "CAMPUS_DATA_DIR=%cd%\.data"

where py >nul 2>nul
if %errorlevel% equ 0 (
  set "PYTHON=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ first.
    exit /b 1
  )
  set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
  %PYTHON% -m venv .venv
  if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo.
".venv\Scripts\python.exe" -m flask --app app init-db
if errorlevel 1 exit /b 1

if /i "%~1"=="--demo" (
  ".venv\Scripts\python.exe" -m flask --app app init-demo
) else (
  ".venv\Scripts\python.exe" -m flask --app app create-owner
)
if errorlevel 1 exit /b 1

echo.
echo Initialization complete. Run start_windows.bat to start the app.
endlocal