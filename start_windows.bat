@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Environment not initialized. Run init_windows.bat first.
  exit /b 1
)

if not defined CAMPUS_DATA_DIR set "CAMPUS_DATA_DIR=%cd%\.data"
if not defined CAMPUS_HOST set "CAMPUS_HOST=127.0.0.1"
if not defined CAMPUS_PORT set "CAMPUS_PORT=5000"
set "CAMPUS_URL=http://%CAMPUS_HOST%:%CAMPUS_PORT%"

echo CampusSmartFlow starting at %CAMPUS_URL%
".venv\Scripts\python.exe" -m waitress --host=%CAMPUS_HOST% --port=%CAMPUS_PORT% --call app:create_app
endlocal