@echo off
rem PBP Studio launcher.
rem Sets up a local Python environment on first run (Pillow + numpy + scipy),
rem then starts the local web app and opens the browser. Nothing is installed system-wide.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo First run - creating a local Python environment...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python -m venv .venv
    ) else (
        goto nopython
    )
)
if not exist ".venv\Scripts\python.exe" goto nopython

echo Installing requirements (one time)...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if not %errorlevel%==0 goto pipfail

:run
echo Starting PBP Studio - http://127.0.0.1:8777/ (close this window to stop)
".venv\Scripts\python.exe" "app\server.py"
goto :eof

:nopython
echo.
echo Python 3.10+ was not found.
echo Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH") and run this file again.
pause
exit /b 1

:pipfail
echo.
echo Could not install the Python requirements. Check your internet connection and try again.
pause
exit /b 1
