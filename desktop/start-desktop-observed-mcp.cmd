@echo off
setlocal
for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "PYTHONPATH=%REPO_ROOT%\app;%PYTHONPATH%"
set "VIRTUAL_ENV="
where uv.exe >nul 2>nul
if errorlevel 1 (
  echo uv.exe not found on PATH. Run Setup-All.cmd first. 1>&2
  exit /b 1
)
uv.exe run --project "%REPO_ROOT%\app" --frozen python -m bridge.mcp_proxy --worker desktop --launcher "%REPO_ROOT%\desktop\start-desktop-mcp.cmd"
exit /b %ERRORLEVEL%
