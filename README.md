# Gesture Gun — 손가락 권총 제스처 슈팅 게임

웹캠 + MediaPipe 기반 손가락 제스처 슈팅 게임입니다.  
**이 저장소는 원본 코드를 GitHub 호스팅에 그대로 보존하며, 웹페이지(index.html)를 통해 소개 및 다운로드/실행 안내를 제공합니다.**

> **주의:** 이 프로젝트는 Python 데스크톱 애플리케이션입니다.  
> 웹 브라우저에서 원본 코드를 수정 없이 직접 실행할 수는 없습니다. 아래 방법으로 로컬 컴퓨터에서 실행하세요.

## 파일 목록 (원본 그대로 보존)

| 파일 | 용도 |
|------|------|
| `main.py` | 게임 메인 코드 (원본 수정 없음) |
| `requirements.txt` | 필수 Python 패키지 (`mediapipe`, `opencv-python`, `pyinstaller`) |
| `hand_landmarker.task` | MediaPipe 손 랜드마크 인식 모델 (바이너리) |
| `gesture_gun_save.json` | 게임 저장 데이터 |
| `index.html` | 웹페이지 소개/다운로드 페이지 (추가) |
| `style.css` | 웹페이지 스타일 (추가) |
| `game.js` | 웹 버전 게임 로직 (추가) |
| `Gesture-Gun.spec` | PyInstaller 실행 파일 빌드 스펙 (추가) |
| `build.bat` | Windows 실행 파일 빌드 스크립트 (추가) |
| `build.sh` | macOS/Linux 실행 파일 빌드 스크립트 (추가) |
| `README.md` | 이 안내 파일 (추가) |

## 1. Python 소스로 직접 실행

1. 저장소를 클론하거나 ZIP으로 다운로드합니다.
2. Python을 설치합니다 (3.8 이상 권장).
3. 프로젝트 폴더로 이동해 필수 라이브러리를 설치합니다.

```bash
pip install -r requirements.txt
```

4. 게임을 실행합니다.

```bash
# 웹캠 모드 (기본)
py main.py

# 마우스로 테스트 모드 (클릭=발사, 우클릭=장전, 휠클릭=무기교체)
py main.py --mouse
```

## 2. 실행 파일(.exe / 앱) 빌드 (Windows / macOS / Linux)

PyInstaller를 사용해 설치 없이 실행할 수 있는 독립 실행 파일을 만듭니다.

### Windows (build.bat)

```powershell
# PowerShell 또는 명령 프롬프트에서
build.bat
```

### macOS / Linux (build.sh)

```bash
chmod +x build.sh
./build.sh
```

빌드 완료 후 생성된 파일:
- Windows: `dist/Gesture-Gun.exe`
- macOS: `dist/Gesture-Gun.app`
- Linux: `dist/Gesture-Gun`

### 수동 빌드 (PyInstaller 직접 실행)

```bash
pip install -r requirements.txt
pyinstaller Gesture-Gun.spec --clean --noconfirm
```

## 3. GitHub Releases에 실행 파일 올리기

빌드된 실행 파일을 GitHub Releases에 배포하려면 아래 단계를 따르세요.

### 3-1. 코드 푸시

```powershell
git init
git add .
git commit -m "최초 커밋: 원본 코드 및 웹/빌드 파일 추가"
git branch -M main
git remote add origin https://github.com/사용자이름/저장소이름.git
git push -u origin main
```

> 원격 저장소에 이미 커밋이 있어 푸시가 거절되면:
> `git pull origin main --allow-unrelated-histories` 후 다시 푸시하세요.

### 3-2. GitHub Releases 생성

1. GitHub 저장소 페이지로 이동합니다.
2. 우측 상단 **Releases** 섹션 → **Draft a new release** 클릭.
3. **Tag version**: 예) `v1.0.0`
4. **Release title**: 예) `Gesture-Gun v1.0.0`
5. **Describe this release**: 간단한 설명 입력.
6. **Assets** 섹션에서 빌드된 실행 파일 업로드:
   - Windows: `dist/Gesture-Gun.exe`
   - macOS: `dist/Gesture-Gun.app` (압축 필요: `.zip`으로 압축)
   - Linux: `dist/Gesture-Gun`
7. **Publish release** 클릭.

### 3-3. 사용자 다운로드 안내

릴리스 페이지에서 사용자는 해당 OS에 맞는 실행 파일을 받아 실행할 수 있습니다.

## 4. 제스처 조작법

- 검지만 펴기(권총 손모양): 조준 (검지 끝이 조준점)
- 엄지 접기: 발사
- 손바닥 활짝 펴고 0.35초: 장전
- 브이(검지+중지): 무기 교체
- 주먹: 방어 (받는 피해 감소)
- HUD 버튼을 0.9초 가리키기: 아이템 사용 / 무기 선택 / 메뉴

키보드:
- `SPACE` 발사 · `R` 장전 · `TAB` 무기교체 · `1~6` 무기선택
- `H` 구급상자 · `A` 방어구 · `P` 일시정지 · `M` 소리 on/off
- `F` 전체화면 · `V` 마우스/카메라 전환 · `ESC` 뒤로가기/종료

## 5. 게임 모드

- PVE 좀비 웨이브
- PVP 2인 대결
- 사격장
- 인벤토리 & 상점

## 라이선스

원본 코드는 수정 없이 그대로 보존됩니다.
