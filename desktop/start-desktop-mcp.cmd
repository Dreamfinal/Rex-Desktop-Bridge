@echo off
setlocal

for %%I in ("%~dp0.") do set "DESKTOP_ROOT=%%~fI"
set "PYTHONUTF8=1"
if not defined REX_DESKTOP_INPUT_ENABLED set "REX_DESKTOP_INPUT_ENABLED=1"

where uv.exe >nul 2>nul
if errorlevel 1 (
  echo uv.exe not found on PATH. Run Setup-All.cmd first. 1>&2
  exit /b 1
)

uv.exe run --project "%DESKTOP_ROOT%" --frozen python "%DESKTOP_ROOT%\desktop_worker.py"
exit /b %ERRORLEVEL%
