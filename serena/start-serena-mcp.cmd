@echo off
setlocal

for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
set "TOP_FS_ALLOWED_ROOTS=%USERPROFILE%"
set "TOP_FS_AUTO_REGISTER=1"
set "PYTHONUTF8=1"
set "TOP_SERENA_PATCH_ENABLED=1"

if defined SERENA_FS_ALLOWED_ROOTS set "TOP_FS_ALLOWED_ROOTS=%SERENA_FS_ALLOWED_ROOTS%"

if defined SERENA_DEFAULT_PROJECT (
  set "SERENA_PROJECT=%SERENA_DEFAULT_PROJECT%"
) else if exist "%USERPROFILE%\Documents\AI_Workspace\Agent-Team" (
  set "SERENA_PROJECT=%USERPROFILE%\Documents\AI_Workspace\Agent-Team"
) else (
  set "SERENA_PROJECT=%REPO_ROOT%"
)

set "SERENA_PROJECT_FWD=%SERENA_PROJECT:\=/%"

where uvx.exe >nul 2>nul
if errorlevel 1 (
  echo uvx.exe not found on PATH. Run Setup-All.cmd first. 1>&2
  exit /b 1
)

uvx --from git+https://github.com/oraios/serena@7fcbca7e62555ec2287ddb2f083caee805848ea6 serena start-mcp-server --context chatgpt --project "%SERENA_PROJECT_FWD%"
exit /b %ERRORLEVEL%
