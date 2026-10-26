@echo off
setlocal
cd /d "%~dp0"
set "OKAN_PYTHON="
set "OKAN_PY_ARGS="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "OKAN_PYTHON=%~dp0.venv\Scripts\python.exe"
  goto ready
)
where py >nul 2>nul
if not errorlevel 1 (
  set "OKAN_PYTHON=py"
  set "OKAN_PY_ARGS=-3"
  goto ready
)
where python >nul 2>nul
if not errorlevel 1 (
  set "OKAN_PYTHON=python"
  goto ready
)
exit /b 9009
:ready
"%OKAN_PYTHON%" %OKAN_PY_ARGS% -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>nul
if errorlevel 1 exit /b 9009
if not exist "%LOCALAPPDATA%\OkanDurak" mkdir "%LOCALAPPDATA%\OkanDurak"
set "OKAN_MODE="
if /i "%~1"=="kiosk" set "OKAN_MODE=--kiosk"
:run
"%OKAN_PYTHON%" %OKAN_PY_ARGS% "%~dp0app.py" %OKAN_MODE% 2>>"%LOCALAPPDATA%\OkanDurak\launcher.log"
set "OKAN_EXIT=%ERRORLEVEL%"
if /i not "%~1"=="kiosk" exit /b %OKAN_EXIT%
if "%OKAN_EXIT%"=="0" exit /b 0
rem Restart only after a crash. The maintenance exit (Ctrl+Shift+Q) stays closed.
timeout /t 5 /nobreak >nul 2>nul
goto run
