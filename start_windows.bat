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
set "CAMPUS_URL=http://%CAMPUS_HOST%:%CAMPUS_PORT%"

powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; @(Get-NetTCPConnection -State Listen -LocalPort %CAMPUS_PORT% -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique) ^| ForEach-Object { Stop-Process -Id $_ -Force }"
if errorlevel 1 (
  echo 错误：无法释放端口 %CAMPUS_PORT%。
  exit /b 1
)

start "" /B powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; try { Start-Process '%CAMPUS_URL%' } catch {}"

echo 校园智享正在启动：%CAMPUS_URL%
".venv\Scripts\python.exe" -m waitress --host=%CAMPUS_HOST% --port=%CAMPUS_PORT% --call app:create_app
endlocal
