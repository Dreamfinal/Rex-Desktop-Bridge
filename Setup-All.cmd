@echo off
setlocal
pushd "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Setup completed successfully.
) else (
  echo Setup failed with exit code %RC%.
)
echo.
pause
popd
exit /b %RC%
