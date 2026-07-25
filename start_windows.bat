@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 错误：环境尚未初始化，请先运行 init_windows.bat。
  exit /b 1
)

if not defined CAMPUS_HOST set "CAMPUS_HOST=127.0.0.1"
if not defined CAMPUS_PORT set "CAMPUS_PORT=5000"

echo 校园智享正在启动：http://%CAMPUS_HOST%:%CAMPUS_PORT%
".venv\Scripts\python.exe" -m waitress --host=%CAMPUS_HOST% --port=%CAMPUS_PORT% --call app:create_app
endlocal
