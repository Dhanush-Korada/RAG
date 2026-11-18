
@echo off
title Python App Launcher


echo =====================================
echo       PYTHON APP LAUNCHER
echo =====================================

:: Create virtual environment if missing
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment...
    py -m venv venv
    if errorlevel 1 goto error
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

:: Check and install missing requirements
if exist "requirements.txt" (
    echo [INFO] Checking installed packages...
    py -m pip install -r requirements.txt
    if errorlevel 1 goto error
) else (
    echo [WARNING] requirements.txt not found!
)

:: Run application
echo.
echo =====================================
echo       STARTING APPLICATION
echo =====================================

streamlit run app.py

pause
exit /b 0

:error
echo.
echo [ERROR] Something went wrong!
pause
exit /b 1
