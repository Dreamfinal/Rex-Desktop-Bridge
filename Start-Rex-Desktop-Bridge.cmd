@echo off
setlocal
for %%I in ("%~dp0.") do set "REPO_ROOT=%%~fI"
set "PYTHONPATH=%REPO_ROOT%\app;%PYTHONPATH%"
where uv.exe >nul 2>nul
if errorlevel 1 (
  echo uv.exe not found on PATH. Run Setup-All.cmd first. 1>&2
  pause
  exit /b 1
)
uv.exe run --project "%REPO_ROOT%\app" --frozen python -m bridge.gui
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
