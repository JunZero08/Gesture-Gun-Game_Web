#!/usr/bin/env bash
# ============================================================
# Gesture-Gun Build Script for macOS / Linux
# ============================================================
set -e

echo "============================================"
echo "Gesture-Gun Build Script (macOS / Linux)"
echo "============================================"
echo

# Detect OS
OS="$(uname -s)"
echo "Detected OS: $OS"

# Remove existing venv and dist to avoid corrupted environment
if [ -d ".venv" ]; then
    echo "[1/5] Removing existing .venv..."
    rm -rf .venv
fi

if [ -d "dist" ]; then
    echo "Removing existing dist..."
    rm -rf dist
fi

if [ -d "build" ]; then
    echo "Removing existing build..."
    rm -rf build
fi

# Create Python virtual environment
echo "[2/5] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install packages
echo "[3/5] Installing packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Run PyInstaller
echo "[4/5] Running PyInstaller build..."
pyinstaller Gesture-Gun.spec --clean --noconfirm

echo
echo "============================================"
echo "[5/5] Build complete!"
echo "============================================"

if [[ "$OS" == "Darwin" ]]; then
    echo "macOS app: dist/Gesture-Gun.app"
    echo "To run:    open dist/Gesture-Gun.app"
elif [[ "$OS" == "Linux" ]]; then
    echo "Linux executable: dist/Gesture-Gun"
    echo "To run:           ./dist/Gesture-Gun"
fi

echo
