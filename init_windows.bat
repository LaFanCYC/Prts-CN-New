@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
  set "PYTHON=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo 错误：未找到 Python，请先安装 Python 3.11 或更高版本。
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
".venv\Scripts\python.exe" -m flask --app app init-db
if errorlevel 1 exit /b 1

if /i "%~1"=="--demo" (
  ".venv\Scripts\python.exe" -m flask --app app init-demo
) else (
  ".venv\Scripts\python.exe" -m flask --app app create-admin
)
if errorlevel 1 exit /b 1

echo 初始化完成。运行 start_windows.bat 启动应用。
endlocal
