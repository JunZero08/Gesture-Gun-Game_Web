#!/usr/bin/env bash
# ============================================================
# Gesture-Gun macOS / Linux 실행 파일 빌드 스크립트
# ============================================================
set -e

echo "[1/4] Python 가상환경 생성 중..."
python3 -m venv .venv
source .venv/bin/activate

echo "[2/4] 필수 패키지 설치 중..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/4] PyInstaller 빌드 실행 중..."
pyinstaller Gesture-Gun.spec --clean --noconfirm

echo "[4/4] 빌드 완료!"
echo
echo "실행 파일 위치: dist/Gesture-Gun"
echo
