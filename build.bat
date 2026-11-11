@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo Gesture-Gun Windows Build Script
echo ============================================
echo.

rem Remove existing venv to avoid corrupted environment
if exist .venv (
    echo [1/4] Removing existing .venv...
    rmdir /s /q .venv
)

echo [1/4] Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment.
    echo Run as Administrator or reinstall Python.
    pause
    exit /b 1
)

echo [2/4] Activating venv and installing packages...
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install packages.
    pause
    exit /b 1
)

echo [3/4] Running PyInstaller build...
pyinstaller Gesture-Gun.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo [4/4] Build complete!
echo Executable: dist\Gesture-Gun.exe
echo ============================================
echo.
pause
