@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "config.json" (
    if not exist "config.example.json" (
        echo [ERROR] config.example.json not found.
        pause
        exit /b 1
    )
    echo Creating config.json from config.example.json ...
    copy /Y "config.example.json" "config.json" >nul
    echo Please edit config.json and set ai.api_key, then run again.
    pause
    exit /b 0
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment ...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"
"venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt

"venv\Scripts\python.exe" main.py
pause
endlocal
