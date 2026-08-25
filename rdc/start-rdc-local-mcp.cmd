@echo off
setlocal

set "RDC_SOURCE=%~dp0"
set "RDC_RUNTIME=%LOCALAPPDATA%\Rex-Desktop-Bridge\rdc"
set "DESKTOP_COMMANDER_CONFIG_DIR=%RDC_RUNTIME%\config"
set "DESKTOP_COMMANDER_DISABLE_TELEMETRY=1"
set "DEBUG_MODE=false"

where node.exe >nul 2>nul
if errorlevel 1 (
  echo node.exe not found on PATH. Run Setup-All.cmd first. 1>&2
  exit /b 1
)

node.exe "%RDC_SOURCE%app\node_modules\@wonderwhy-er\desktop-commander\dist\index.js" --no-onboarding
exit /b %ERRORLEVEL%
