#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GESTURE GUN  -  손가락 권총 제스처 슈팅 게임 (웹캠 + MediaPipe)

모드: PVE 좀비 웨이브 / PVP 2인 대결 / 사격장 / 인벤토리 & 상점
실행: py main.py            (웹캠)
      py main.py --mouse    (마우스로 테스트: 클릭=발사, 우클릭=장전, 휠클릭=무기교체)

[제스처]
  검지만 펴기(권총 손모양)   조준 (검지 끝이 조준점)
  엄지 접기                  발사 (총기마다 단발/연사)
  손바닥 활짝 펴고 0.35초    장전
  브이(검지+중지)            무기 교체
  주먹                       방어 (받는 피해 감소)
  HUD 버튼을 0.9초 가리키기  아이템 사용 / 무기 선택 / 메뉴

[키보드]
  SPACE 발사   R 장전   TAB 무기교체   1~6 무기선택   H 구급상자   A 방어구
  P 일시정지   M 소리 on/off   F 전체화면   K 손뼈대   I 디버그   V 마우스/카메라
  G (마우스 모드) 방어 on/off   B (PVP) 봇 대전 on/off   N (튜토리얼) 다음 단계
  메뉴의 TUTORIAL 에서 제스처 연습과 방아쇠(엄지) 보정을 할 수 있습니다.
  ESC 뒤로가기(메뉴에서는 종료)

필요: opencv-python, numpy, mediapipe (카메라 모드)
소리: Windows는 winsound, macOS(afplay)/Linux(paplay, aplay)는 자동으로 사용
"""
import argparse
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import wave
from collections import deque

import numpy as np
import cv2

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, "hand_landmarker.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
SAVE_PATH = os.path.join(BASE, "gesture_gun_save.json")
WIN = "Gesture Gun"
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_B = cv2.FONT_HERSHEY_DUPLEX

# ===================== 튜닝 값 (제스처가 잘 안 맞으면 여기를 조절) =====================
EXT_RATIO = 1.40          # 손가락이 펴졌다고 보는 (끝-손목)/(뿌리-손목) 거리 비율
EXT_RATIO_PINKY = 1.30    # 새끼손가락은 짧아서 조금 낮게
TRIG_DOWN = 0.40          # 엄지끝-검지뿌리 거리 / 손바닥 길이 이하면 '방아쇠 당김(발사)'
TRIG_UP = 0.55            # 이 이상이면 '방아쇠 놓음(재장전 준비)'
PUNCH_DOWN = 0.45         # 손이 카메라 쪽으로 급격히 가까워지면 '펀치 포워드(발사)'
PUNCH_UP = 0.70           # 이 이상이면 펀치 종료(재발사 준비)
MELEE_COOLDOWN = 0.5      # 근접 공격 쿨다운(초)
MELEE_RANGE = 120         # 근접 공격 판정 거리 (피셀, draw에서 S() 적용)
MELEE_DMG = 40            # 근접 공격 기본 데미지
MELEE_COMBO_MAX = 5       # 최대 콤보 수
MELEE_COMBO_BONUS = 1.2   # 콤보 데미지 배수
MELEE_COMBO_TIMEOUT = 1.5 # 콤보 유지 시간(초)
AIM_LOCK_BACK = 0.07      # 발사 순간 조준점을 이 시간(초) 전 위치로 고정
DWELL_TIME = 0.9          # HUD 버튼 가리키기 시간
PALM_RELOAD = 0.35        # 손바닥 장전 유지 시간
RENDER_MAX_W = 1600       # 렌더링 최대 가로 해상도 (창이 더 커도 이 값으로 그린 뒤 늘림)
RENDER_MIN_W = 480
INF = 10 ** 6

# --- 제스처 인식 개선용 값 ---
EXT_HYST = 0.18           # 손가락이 '접혔다'고 보려면 (EXT_RATIO - EXT_HYST) 아래로 내려가야 함 (깜빡임 방지)
ANG_ON = 148.0            # 손가락 관절 평균 각도(도)가 이 이상이어야 '펴짐' 후보
ANG_OFF = 128.0           # 이 이하로 내려가면 '접힘'
LOST_GRACE = 0.18         # 손을 잠깐(초) 놓쳐도 이전 상태를 유지
GESTURE = dict(trig_down=TRIG_DOWN, trig_up=TRIG_UP)   # 튜토리얼 보정으로 사용자별로 덮어씀

# --- 건 포즈 (총 모집) 감지 상수 ---
GUN_POSE_IDX_EXT_RATIO = 1.35   # 검지가 펴졌다고 보는 기준
GUN_POSE_THUMB_UP_RATIO = 0.55  # 엄지가 위로 솟았을 때 (검지뿌리 대비)
GUN_POSE_OTHER_FOLD_RATIO = 1.10  # 중지/약지/새끼가 접혔을 때 기준

# --- 탕-탕 발포 모션 (건 포즈 상태에서 손 빠르게 앞뒤로) ---
TAP_TAP_FORWARD_THRESH = 0.30   # 손이 앞으로 밀려감 (카메라 가까움)
TAP_TAP_BACK_THRESH = 0.20      # 손이 뒤로 빠짐 (카메라 멀어짐)
TAP_TAP_MAX_INTERVAL = 0.35     # 두 탭 사이의 최대 간격(초)

# --- 시선 고정 (게이즈 에이밍) 상수 ---
GAZE_LOCK_TIME = 0.50           # 시선을 고정하여 타겟 락온까지 걸리는 시간(초)
GAZE_LOCK_DIST = 90             # 시선과 타겟이 이 거리 이내면 락온 가능(픽셀)
GAZE_LOCK_ANGLE = 0.35          # 시선 방향과 타겟 방향이 이 라디안 이내면 락온

# 난이도: 좀비 체력/공격력/코인 배율
DIFFS = [
    dict(name="EASY", zhp=0.75, zdmg=0.6, coin=1.0, spawn=1.25),
    dict(name="NORMAL", zhp=1.0, zdmg=1.0, coin=1.0, spawn=1.0),
    dict(name="HARD", zhp=1.4, zdmg=1.5, coin=1.3, spawn=0.8),
]


# ===================== 화면 크기(유동 해상도) =====================
class View:
    def __init__(self):
        self.W, self.H, self.s = 1280, 720, 1.0

    def set(self, W, H):
        self.W, self.H = int(W), int(H)
        self.s = max(0.5, min(2.4, self.H / 720.0))


V = View()


def S(v):
    """720p 기준 픽셀 값을 현재 해상도에 맞게 변환"""
    return int(round(v * V.s))


def T(th):
    return max(1, int(round(th * V.s)))


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def C(c):
    return (int(clamp(c[0], 0, 255)), int(clamp(c[1], 0, 255)), int(clamp(c[2], 0, 255)))


def P2(p):
    return (int(p[0]), int(p[1]))


def inside(r, p):
    return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


def text(img, s, x, y, size=0.6, col=(255, 255, 255), th=1, anchor="l", font=FONT):
    sc = size * V.s
    t = T(th)
    (tw, _), _ = cv2.getTextSize(s, font, sc, t)
    x, y = int(x), int(y)
    if anchor == "c":
        x -= tw // 2
    elif anchor == "r":
        x -= tw
    cv2.putText(img, s, (x, y), font, sc, (0, 0, 0), t + max(1, int(round(2 * V.s))), cv2.LINE_AA)
    cv2.putText(img, s, (x, y), font, sc, C(col), t, cv2.LINE_AA)
    return tw


def shade(img, x0, y0, x1, y1, col=(0, 0, 0), a=0.5):
    H, W = img.shape[:2]
    x0, x1 = clamp(int(x0), 0, W), clamp(int(x1), 0, W)
    y0, y1 = clamp(int(y0), 0, H), clamp(int(y1), 0, H)
    if x1 <= x0 or y1 <= y0:
        return
    roi = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = cv2.addWeighted(roi, 1 - a, np.full_like(roi, C(col)), a, 0)


def bar(img, x, y, w, h, frac, col, back=(40, 40, 40), border=(210, 210, 210)):
    frac = clamp(frac, 0, 1)
    cv2.rectangle(img, (x, y), (x + w, y + h), back, -1)
    if frac > 0:
        cv2.rectangle(img, (x, y), (x + int(w * frac), y + h), C(col), -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), border, 1)


def crosshair(img, p, r, col=(255, 255, 255), th=2):
    x, y = int(p[0]), int(p[1])
    g = max(2, r // 3)
    th = max(1, th)
    cv2.circle(img, (x, y), r, C(col), th, cv2.LINE_AA)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(img, (x + dx * g, y + dy * g), (x + dx * (r + g), y + dy * (r + g)), C(col), th, cv2.LINE_AA)
    cv2.circle(img, (x, y), max(1, th), C(col), -1, cv2.LINE_AA)


def btn_draw(img, rect, label, hover=False, sel=False, col=(70, 70, 70), prog=0.0, size=0.7, enabled=True, sub=None):
    x0, y0, x1, y1 = [int(v) for v in rect]
    base = col if enabled else (45, 45, 45)
    if hover and enabled:
        base = tuple(min(255, c + 45) for c in base)
    shade(img, x0, y0, x1, y1, base, 0.82)
    edge = (0, 255, 255) if sel else ((255, 255, 255) if (hover and enabled) else (150, 150, 150))
    cv2.rectangle(img, (x0, y0), (x1, y1), edge, T(2) if (hover or sel) else 1)
    tc = (255, 255, 255) if enabled else (150, 150, 150)
    cy = (y0 + y1) // 2
    if sub:
        text(img, label, (x0 + x1) // 2, cy - S(2), size, tc, anchor="c")
        text(img, sub, (x0 + x1) // 2, cy + S(16), size * 0.62, (200, 200, 200), anchor="c")
    else:
        text(img, label, (x0 + x1) // 2, cy + int(S(9) * size / 0.7), size, tc, anchor="c")
    if prog > 0:
        bar(img, x0 + 2, y1 - S(8), (x1 - x0) - 4, S(6), prog, (0, 255, 0), (30, 30, 30), (30, 30, 30))


# ===================== 사운드 (Windows winsound / macOS afplay / Linux paplay·aplay) =====================
SR = 22050


def _wav(x):
    pcm = (np.clip(x, -1, 1) * 32767 * 0.55).astype("<i2")
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return bio.getvalue()


def _t(d):
    return np.linspace(0, d, int(SR * d), endpoint=False)


def _noise(d, decay, lp=0):
    t = _t(d)
    n = np.random.uniform(-1, 1, len(t)) * np.exp(-t * decay)
    if lp > 1:
        n = np.convolve(n, np.ones(lp) / lp, mode="same")
    return n


def _tone(f, d, decay):
    t = _t(d)
    return np.sin(2 * np.pi * f * t) * np.exp(-t * decay)


def _cat(*a):
    return np.concatenate(a)


def _silence(d):
    return np.zeros(int(SR * d))


class Sfx:
    def __init__(self, on=True):
        self.on = on
        self.ws = None          # Windows winsound 모듈
        self.cmd = None         # 그 외 OS의 재생 명령
        self.dir = None
        self.files = {}
        self.procs = []
        self.data = {}
        try:
            import winsound
            self.ws = winsound
        except Exception:
            for c in (["afplay"], ["paplay"], ["aplay", "-q"]):
                if shutil.which(c[0]):
                    self.cmd = c
                    break
            if self.cmd is None:
                return
        try:
            t = _t(0.2)

            def _env(d, attack=0.005, decay=0.15):
                n = int(SR * d)
                env = np.ones(n)
                a = max(1, int(SR * attack))
                env[:a] = np.linspace(0, 1, a)
                env[a:] = np.exp(-np.arange(n - a) / (SR * decay))
                return env

            def _gunshot(dur, noise_decay, low_freq, high_freq, noise_amp=0.9, low_amp=0.5, high_amp=0.35):
                n = int(SR * dur)
                tt = np.arange(n) / SR
                # 소음 버스트 (총발화음)
                nz = np.random.uniform(-1, 1, n) * np.exp(-tt * noise_decay)
                # 저음 뻥 소리 (총구 공명)
                low = np.sin(2 * np.pi * low_freq * tt) * np.exp(-tt * 40)
                # 고음 파열음 (탄환 발사 크랙)
                high = np.sin(2 * np.pi * high_freq * tt) * np.exp(-tt * 80)
                mix = nz * noise_amp + low * low_amp + high * high_amp
                return mix * _env(dur)

            self.data = {
                "shot": _wav(_gunshot(0.18, 45, 110, 900)),
                "smg": _wav(_gunshot(0.09, 70, 160, 1100)),
                "shotgun": _wav(_gunshot(0.35, 12, 60, 500, noise_amp=1.0, low_amp=0.8, high_amp=0.5)),
                "sniper": _wav(_gunshot(0.45, 8, 50, 300, noise_amp=0.8, low_amp=1.0, high_amp=0.4)),
                "empty": _wav(_tone(1500, 0.05, 100) * 0.4),
                "reload": _wav(_cat(_tone(400, 0.06, 100), _silence(0.12), _tone(650, 0.07, 100))),
                "hit": _wav(_tone(800, 0.06, 80) * 0.7 + _noise(0.04, 100) * 0.4),
                "melee": _wav(_noise(0.12, 60, 5) * 0.8 + _tone(120, 0.12, 40) * 0.5),
                "kill": _wav(np.sin(2 * np.pi * (500 * t - 1200 * t ** 2)) * np.exp(-t * 10) * 0.8),
                "hurt": _wav(_tone(100, 0.25, 25) + _noise(0.25, 30, 10) * 0.7),
                "boom": _wav(_cat(_noise(0.8, 5, 20) * 1.1, _tone(40, 0.8, 8) * 0.9)),
                "coin": _wav(_cat(_tone(1100, 0.08, 50), _tone(1700, 0.12, 40))),
                "ui": _wav(_tone(650, 0.05, 90) * 0.5),
                "beep": _wav(_tone(850, 0.09, 60) * 0.5),
                "go": _wav(_tone(1300, 0.25, 10) * 0.7),
                "win": _wav(_cat(_tone(550, 0.12, 15), _tone(800, 0.12, 15), _tone(1100, 0.3, 10))),
            }
            # 모든 OS에서 임시 WAV 파일 생성 (winsound SND_FILENAME용)
            self.dir = tempfile.mkdtemp(prefix="gesture_gun_")
            for k, v in self.data.items():
                p = os.path.join(self.dir, k + ".wav")
                with open(p, "wb") as f:
                    f.write(v)
                self.files[k] = p
        except Exception:
            self.data = {}
            self.cmd = None

    def play(self, name):
        if not self.on or name not in self.data:
            return
        try:
            if self.ws is not None:
                self.ws.PlaySound(self.files[name], self.ws.SND_FILENAME | self.ws.SND_ASYNC)
            elif self.cmd is not None:
                self.procs = [p for p in self.procs if p.poll() is None]
                if len(self.procs) >= 6:
                    return
                self.procs.append(subprocess.Popen(self.cmd + [self.files[name]],
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except Exception:
            pass

    def close(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)


# ===================== 이펙트 =====================
class FX:
    def __init__(self):
        self.p, self.t, self.rings = [], [], []
        self.shake = 0.0
        self.hurt = 0.0
        self.flash = 0.0

    def burst(self, x, y, col, n=10, speed=240, life=0.5, size=3, grav=600):
        if len(self.p) > 700:
            return
        for _ in range(n):
            a = random.uniform(0, 6.283)
            sp = random.uniform(0.2, 1.0) * speed * V.s
            self.p.append([x, y, math.cos(a) * sp, math.sin(a) * sp, life * random.uniform(0.6, 1.2), life,
                           col, max(1.0, size * V.s), grav * V.s])

    def text(self, x, y, s, col=(255, 255, 255), size=0.7):
        self.t.append([x, y, 0.9, s, col, size])

    def ring(self, x, y, r, col, life=0.4):
        self.rings.append([x, y, r, col, life, life])

    def update(self, dt):
        for p in self.p:
            p[3] += p[8] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.p = [p for p in self.p if p[4] > 0]
        for t in self.t:
            t[1] -= 55 * V.s * dt
            t[2] -= dt
        self.t = [t for t in self.t if t[2] > 0]
        for r in self.rings:
            r[4] -= dt
        self.rings = [r for r in self.rings if r[4] > 0]
        self.shake = max(0.0, self.shake - 40 * dt)
        self.hurt = max(0.0, self.hurt - dt * 1.2)
        self.flash = max(0.0, self.flash - dt * 2.5)

    def draw(self, img):
        for r in self.rings:
            k = 1 - r[4] / r[5]
            cv2.circle(img, P2(r[:2]), max(1, int(r[2] * (0.3 + 0.7 * k))), C(r[3]), T(3), cv2.LINE_AA)
        for p in self.p:
            k = clamp(p[4] / p[5], 0, 1)
            c = tuple(int(v * (0.35 + 0.65 * k)) for v in p[6])
            cv2.circle(img, P2(p[:2]), max(1, int(p[7] * (0.4 + 0.6 * k))), c, -1, cv2.LINE_AA)
        for t in self.t:
            text(img, t[3], t[0], t[1], t[5], t[4], 2, "c")


# ===================== 입력 컨트롤러 =====================
FINGERS = ((8, 5), (12, 9), (16, 13), (20, 17))
# (뿌리 MCP, PIP, DIP, 끝 TIP) : 검지, 중지, 약지, 새끼
FINGER_IDS = ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))


class OneEuro:
    """One Euro 필터: 천천히 움직일 땐 강하게 떨림을 잡고, 빠르게 움직일 땐 지연 없이 따라감"""

    def __init__(self, mincut=1.6, beta=0.015, dcut=1.0):
        self.mincut, self.beta, self.dcut = mincut, beta, dcut
        self.x = None
        self.dx = (0.0, 0.0)

    def reset(self):
        self.x = None
        self.dx = (0.0, 0.0)

    @staticmethod
    def _a(cut, dt):
        return 1.0 / (1.0 + (1.0 / (2.0 * math.pi * cut)) / dt)

    def __call__(self, p, dt):
        dt = max(dt, 1e-3)
        if self.x is None:
            self.x = (float(p[0]), float(p[1]))
            self.dx = (0.0, 0.0)
            return self.x
        ad = self._a(self.dcut, dt)
        rx = (p[0] - self.x[0]) / dt / V.s
        ry = (p[1] - self.x[1]) / dt / V.s
        dx = (self.dx[0] + (rx - self.dx[0]) * ad, self.dx[1] + (ry - self.dx[1]) * ad)
        a = self._a(self.mincut + self.beta * math.hypot(dx[0], dx[1]), dt)
        self.x = (self.x[0] + (p[0] - self.x[0]) * a, self.x[1] + (p[1] - self.x[1]) * a)
        self.dx = dx
        return self.x
CONN = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


class Ctl:
    """손 / 마우스 / 봇이 공유하는 입력 인터페이스"""

    def __init__(self):
        self.present = False
        self.pos = (0.0, 0.0)
        self.lock = (0.0, 0.0)
        self.tip = (0.0, 0.0)
        self.center = (0.0, 0.0)
        self.size = 60.0
        self.dir = (0.0, -1.0)
        self.pose = "NONE"
        self.trigger = False
        self.fire_edge = False
        self.reload_edge = False
        self.switch_edge = False
        self.guard = False
        self.palm_prog = 0.0
        self.pts = None
        self.dbg = ""
        self.tr = 0.0                 # 엄지-검지뿌리 거리 비율 (방아쇠 측정값)
        self.ext = [False] * 4        # 검지/중지/약지/새끼 펴짐 상태

        # --- 건 포즈 (총 모집) 상태 ---
        self.gun_pose = False         # 검지 펴고 엄지 위로 = 총 모집 자세
        self.gun_pose_stable = False  # 건 포즈가 일정 프레임 유지됨
        self.gun_pose_n = 0           # 건 포즈 연속 프레임 수

        # --- 탕-탕 발포 모션 (건 포즈 중 손 앞뒤로 빠르게) ---
        self.tap_z = None             # 손 깊이(z) 이전 값
        self.tap_state = 0            # 0=대기, 1=앞으로 밀었음, 2=뒤로 빠짐(발사)
        self.tap_time = 0.0           # 마지막 탭 시간
        self.tap_count = 0            # 연속 탭 카운트

        # --- 시선 고정 (게이즈 에이밍) ---
        self.gaze_target = None       # 현재 시선이 고정된 적 객체
        self.gaze_lock_t = 0.0        # 시선 고정 시작 시간
        self.gaze_locked = False      # 락온 완료 여부

        # --- 반동 ---
        self.recoil = 0.0
        self.recoil_dir = (0.0, -1.0)

    def shot_pos(self):
        base = self.lock if self.fire_edge else self.pos
        if getattr(self, "recoil", 0.0) > 0:
            rx, ry = getattr(self, "recoil_dir", (0.0, -1.0))
            return (base[0] + rx * self.recoil * S(10), base[1] + ry * self.recoil * S(10))
        return base

    def gaze_target_pos(self):
        """시선 고정 타겟의 현재 위치 반환"""
        if self.gaze_target is not None and hasattr(self.gaze_target, 'center'):
            return self.gaze_target.center
        return self.pos


class HandCtl(Ctl):
    # 포즈를 확정하는 데 필요한 연속 프레임 수 (실수로 장전/방어/교체가 나가지 않도록 포즈별로 다르게)
    NEED = {"GUN": 2, "OTHER": 2, "PALM": 3, "FIST": 3, "PEACE": 4}

    def __init__(self):
        super().__init__()
        self.raw = "NONE"
        self.raw_n = 0
        self.trig = False
        self.armed = False
        self.hist = deque(maxlen=20)
        self.filt = OneEuro()
        self.smooth = None
        self.palm_t = None
        self.palm_used = False
        self.peace_prev = False
        self.switch_cd = 0.0
        self.fext = [False] * 4     # 손가락별 펴짐 상태(히스테리시스용)
        self.lost_t = 0.0
        # 엄지 트리거 상태 (방아쇠) - 유지
        self.trig = False
        self.armed = False
        # 손 전체 펀치 모션 상태 (카메라 쪽으로 손 밀기 = 발사)
        self.punch_z = None
        self.punch_fired = False
        # 근접 공격 상태 (복싱 잽: 앞으로 밀었다가 빠르게 되돌리기)
        self.melee_z = None
        self.melee_fired = False
        self.melee_ready = True
        self.melee_cool = 0.0
        self.melee_combo = 0
        self.melee_combo_t = 0.0
        # 건 포즈 (총 모집) 상태
        self.gun_pose = False
        self.gun_pose_stable = False
        self.gun_pose_n = 0
        # 탕-탕 발포 모션 (건 포즈 중 손 앞뒤로 빠르게)
        self.tap_z = None
        self.tap_state = 0
        self.tap_time = 0.0
        self.tap_count = 0
        # 시선 고정 (게이즈 에이밍)
        self.gaze_target = None
        self.gaze_lock_t = 0.0
        self.gaze_locked = False
        # 시선 고정용 타겟 리스트 (게임에서 설정)
        self.ar_targets = None
        # 반동
        self.recoil = 0.0
        self.recoil_dir = (0.0, -1.0)

    def _lost(self):
        self.present = False
        self.pose = self.raw = "NONE"
        self.raw_n = 0
        self.trigger = self.trig = self.armed = self.guard = False
        self.hist.clear()
        self.filt.reset()
        self.smooth = None
        self.pts = None
        self.palm_t = None
        self.palm_used = False
        self.palm_prog = 0.0
        self.peace_prev = False
        self.fext = [False] * 4
        self.ext = [False] * 4
        self.tr = 0.0
        self.lost_t = 0.0
        self.trig = False
        self.armed = False
        self.punch_z = None
        self.punch_fired = False
        self.melee_z = None
        self.melee_fired = False
        self.melee_ready = True
        self.melee_cool = 0.0
        self.melee_combo = 0
        self.melee_combo_t = 0.0
        # 건 포즈 상태 초기화
        self.gun_pose = False
        self.gun_pose_stable = False
        self.gun_pose_n = 0
        # 탕-탕 상태 초기화
        self.tap_z = None
        self.tap_state = 0
        self.tap_time = 0.0
        self.tap_count = 0
        # 시선 고정 초기화
        self.gaze_target = None
        self.gaze_lock_t = 0.0
        self.gaze_locked = False
        self.ar_targets = None
        # 반동 초기화
        self.recoil = 0.0
        self.recoil_dir = (0.0, -1.0)

    def update(self, lm, now, dt):
        self.fire_edge = self.reload_edge = self.switch_edge = False
        if lm is None:
            self.lost_t += dt
            if self.present and self.lost_t < LOST_GRACE:
                return                      # 잠깐 놓친 프레임: 이전 상태 그대로 유지
            self._lost()
            return
        self.lost_t = 0.0
        W, H = V.W, V.H
        P = [(p.x * W, p.y * H, p.z * W) for p in lm]

        def d3(i, j):
            a, b = P[i], P[j]
            return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

        def ang(a, b, c):
            """b 관절에서 a-b-c 가 이루는 각도(도). 곧게 펴지면 180"""
            v1 = (P[a][0] - P[b][0], P[a][1] - P[b][1], P[a][2] - P[b][2])
            v2 = (P[c][0] - P[b][0], P[c][1] - P[b][1], P[c][2] - P[b][2])
            n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
            n2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
            if n1 < 1e-6 or n2 < 1e-6:
                return 180.0
            cs = clamp((v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2), -1.0, 1.0)
            return math.degrees(math.acos(cs))

        palm = max(d3(0, 9), 1.0)

        # 엄지 트리거 거리 (건 포즈 판정에도 사용)
        tr = d3(4, 5) / palm
        self.tr = tr

        # 손가락 펴짐: (손목 기준 길이 비율) + (관절 각도), 켜짐/꺼짐 기준을 다르게 해서 깜빡임 방지
        ext, rat, angs = [], [], []
        for k, (mcp, pip, dip, tip) in enumerate(FINGER_IDS):
            r = d3(tip, 0) / max(d3(mcp, 0), 1.0)
            a = 0.5 * (ang(mcp, pip, dip) + ang(pip, dip, tip))
            on = EXT_RATIO_PINKY if k == 3 else EXT_RATIO
            off = on - EXT_HYST
            if self.fext[k]:
                e = not (r < off or a < ANG_OFF)
            else:
                e = r > on and a > ANG_ON
            self.fext[k] = e
            ext.append(e)
            rat.append(r)
            angs.append(a)
        self.ext = list(ext)
        i, m, r_, pk = ext
        if i and m and r_ and pk:
            raw = "PALM"
        elif i and m and not r_ and not pk:
            raw = "PEACE"
        elif i and not m and not r_ and not pk:
            raw = "GUN"
        elif not any(ext):
            raw = "FIST"
        else:
            raw = "OTHER"
        if raw == self.raw:
            self.raw_n += 1
        else:
            self.raw, self.raw_n = raw, 1
        if raw != self.pose and self.raw_n >= self.NEED.get(raw, 2):
            self.pose = raw
        self.present = True
        self.guard = self.pose == "FIST"

        # ---------- 건 포즈 (총 모집) 감지 ----------
        # 검지 펴고, 엄지 위로, 나머지 손가락 접힘 = 총 모집 자세
        gun_pose_candidate = (
            self.ext[0] and                                  # 검지 펴짐
            not self.ext[1] and not self.ext[2] and not self.ext[3] and  # 나머지 접힘
            tr > GUN_POSE_THUMB_UP_RATIO                      # 엄지가 위로 (검지뿌리 대비 거리)
        )
        if gun_pose_candidate:
            self.gun_pose_n += 1
        else:
            self.gun_pose_n = 0
        self.gun_pose = gun_pose_candidate
        self.gun_pose_stable = self.gun_pose_n >= 3  # 3프레임 연속으로 건 포즈 유지

        # ---------- 탕-탕 발포 모션 (건 포즈 중 손 앞뒤로 빠르게) ----------
        cz = P[9][2]  # 손 중심 깊이(z)
        tap_fired = False
        if self.gun_pose_stable:
            if self.tap_z is not None:
                dz = self.tap_z - cz  # 양수 = 앞으로 밀림(카메라 가까움)
                if self.tap_state == 0 and dz > TAP_TAP_FORWARD_THRESH:
                    self.tap_state = 1  # 앞으로 밀었음
                elif self.tap_state == 1 and dz < -TAP_TAP_BACK_THRESH:
                    # 뒤로 빠지면 탭 완성
                    self.tap_state = 0
                    now_t = now
                    if self.tap_time > 0 and now_t - self.tap_time <= TAP_TAP_MAX_INTERVAL:
                        self.tap_count += 1
                        if self.tap_count >= 2:
                            tap_fired = True
                            self.tap_count = 0
                    else:
                        self.tap_count = 1
                    self.tap_time = now_t
            self.tap_z = cz
        else:
            self.tap_z = cz
            self.tap_state = 0
            self.tap_time = 0.0
            self.tap_count = 0

        # ---------- 시선 고정 (게이즈 에이밍) ----------
        # 건 포즈 중이고 시선이 적을 향하면 락온
        self.gaze_target = None
        self.gaze_locked = False
        if self.gun_pose_stable and self.ar_targets is not None:
            best = None
            best_d = GAZE_LOCK_DIST
            for zb in self.ar_targets:
                zb_c = zb.center
                d = math.hypot(self.pos[0] - zb_c[0], self.pos[1] - zb_c[1])
                if d < best_d:
                    # 시선 방향과 타겟 방향 체크
                    dir_to_target = (zb_c[0] - self.pos[0], zb_c[1] - self.pos[1])
                    d_len = math.hypot(dir_to_target[0], dir_to_target[1]) or 1.0
                    dir_to_target = (dir_to_target[0] / d_len, dir_to_target[1] / d_len)
                    dot = self.dir[0] * dir_to_target[0] + self.dir[1] * dir_to_target[1]
                    angle = math.acos(clamp(dot, -1.0, 1.0))
                    if angle < GAZE_LOCK_ANGLE:
                        best_d = d
                        best = zb
            self.gaze_target = best
            if best is not None:
                if self.gaze_lock_t == 0.0:
                    self.gaze_lock_t = now
                if now - self.gaze_lock_t >= GAZE_LOCK_TIME:
                    self.gaze_locked = True
            else:
                self.gaze_lock_t = 0.0

        # 조준점: 검지 끝 (One Euro 필터)
        self.smooth = self.filt((P[8][0], P[8][1]), dt)
        self.pos = self.tip = self.smooth
        self.hist.append((now, self.smooth[0], self.smooth[1]))
        self.center = (P[9][0], P[9][1])
        self.size = palm
        dx, dy = P[8][0] - P[5][0], P[8][1] - P[5][1]
        ln = math.hypot(dx, dy)
        if ln > 4:
            nd = (dx / ln, dy / ln)
            ox, oy = self.dir
            vx, vy = ox + (nd[0] - ox) * 0.5, oy + (nd[1] - oy) * 0.5
            vl = math.hypot(vx, vy) or 1.0
            self.dir = (vx / vl, vy / vl)
        self.pts = [(int(p[0]), int(p[1])) for p in P]

        # 엄지 트리거 (방아쇠) 인식 - 선택 사항 (원하면 사용)
        # tr와 self.tr는 이미 위에서 계산됨 (건 포즈 판정용)
        prev_trig = self.trig
        fired = False

        if raw == "GUN":
            if tr > TRIG_UP:
                self.armed = True
            if self.armed:
                if not self.trig and tr < TRIG_DOWN:
                    self.trig = True
                    fired = True
                elif self.trig and tr > TRIG_UP:
                    self.trig = False
            else:
                self.trig = False
        else:
            self.armed = False
            self.trig = False

        # 손 전체 펀치 모션 인식 (주요 발사 방식)
        # 손 중심(9)의 z 값이 급격히 작아지면(카메라 쪽으로 손 밀어냄) 발사
        cz = P[9][2]
        punch_fired = False
        if self.punch_z is not None:
            dz = self.punch_z - cz  # 양수면 카메라에 가까워짐(펀치)
            if dz > PUNCH_DOWN:
                punch_fired = True
        self.punch_z = cz

        # 근접 공격 인식 (복싱 잽: 손 내밀었다가 빠르게 되돌리기)
        melee_fired = False
        if self.melee_ready:
            if self.melee_z is not None:
                dz_melee = self.melee_z - cz  # 앞으로 밀었음
                if dz_melee > PUNCH_DOWN * 0.7:
                    # 이미 앞으로 밀었는데 다시 뒤로 빠지면 잽 완성
                    if cz > self.melee_z + PUNCH_DOWN * 0.3:
                        melee_fired = True
                        self.melee_ready = False
                        self.melee_cool = MELEE_COOLDOWN
                        # 콤보 증가
                        if now - self.melee_combo_t <= MELEE_COMBO_TIMEOUT:
                            self.melee_combo = min(MELEE_COMBO_MAX, self.melee_combo + 1)
                        else:
                            self.melee_combo = 1
                        self.melee_combo_t = now
            self.melee_z = cz
        else:
            self.melee_cool -= dt
            if self.melee_cool <= 0:
                self.melee_ready = True
                self.melee_z = cz
        # 콤보 타임아웃 체크
        if self.melee_combo > 0 and now - self.melee_combo_t > MELEE_COMBO_TIMEOUT:
            self.melee_combo = 0

        # 세 가지 발사 방식 중 하나라도 감지되면 발사
        self.trigger = self.trig or fired or punch_fired or tap_fired
        self.fire_edge = fired or punch_fired or tap_fired
        self.melee_edge = melee_fired

        # 시선 고정 시 조준점을 타겟으로
        aim_pos = self.pos
        if self.gaze_locked and self.gaze_target is not None:
            aim_pos = self.gaze_target.center

        # 반동 적용 (발사 시 손 전체가 뒤로 튕기는 모션)
        if self.fire_edge:
            self.recoil = min(1.0, self.recoil + 0.50)
            self.recoil_dir = self.dir
        else:
            self.recoil = max(0.0, self.recoil - dt * 8.0)

        self.lock = aim_pos
        if self.fire_edge:
            for t, x, y in reversed(self.hist):
                if t <= now - AIM_LOCK_BACK:
                    self.lock = (x, y)
                    break
            else:
                self.lock = (self.hist[0][1], self.hist[0][2])
            if self.gaze_locked and self.gaze_target is not None:
                self.lock = self.gaze_target.center

        # 장전: 손바닥 유지
        if self.pose == "PALM":
            if self.palm_t is None:
                self.palm_t = now
            self.palm_prog = clamp((now - self.palm_t) / PALM_RELOAD, 0, 1)
            if not self.palm_used and now - self.palm_t >= PALM_RELOAD:
                self.reload_edge = True
                self.palm_used = True
        else:
            self.palm_t = None
            self.palm_used = False
            self.palm_prog = 0.0
        # 무기 교체: 브이
        pe = self.pose == "PEACE"
        if pe and not self.peace_prev and now >= self.switch_cd:
            self.switch_edge = True
            self.switch_cd = now + 0.6
        self.peace_prev = pe
        punch_dbg = 0.0 if self.punch_z is None else (self.punch_z - cz)
        melee_dbg = 0.0 if self.melee_z is None else (self.melee_z - cz)
        self.dbg = "%s  idx%.2f/%d mid%.2f/%d rng%.2f/%d pnk%.2f/%d  thumb=%.2f arm=%d punch=%.2f melee=%.2f %s" % (
            self.pose, rat[0], angs[0], rat[1], angs[1], rat[2], angs[2], rat[3], angs[3],
            self.tr, 1 if self.armed else 0, punch_dbg, melee_dbg, "FIRE" if self.trigger else "")


class MouseCtl(Ctl):
    def __init__(self):
        super().__init__()
        self.present = True
        self.mx = V.W // 2
        self.my = V.H // 2
        self.down = False
        self.prev = False
        self.req_reload = False
        self.req_switch = False
        self.size = 55.0

    def event(self, ev, x, y, flags):
        self.mx, self.my = x, y
        if ev == cv2.EVENT_LBUTTONDOWN:
            self.down = True
        elif ev == cv2.EVENT_LBUTTONUP:
            self.down = False
        elif ev == cv2.EVENT_RBUTTONDOWN:
            self.req_reload = True
        elif ev == cv2.EVENT_MBUTTONDOWN:
            self.req_switch = True

    def update(self, lm_unused, now, dt):
        self.present = True
        self.pos = self.tip = self.center = self.lock = (float(self.mx), float(self.my))
        self.trigger = self.down
        self.fire_edge = self.down and not self.prev
        self.prev = self.down
        self.reload_edge, self.req_reload = self.req_reload, False
        self.switch_edge, self.req_switch = self.req_switch, False
        self.pose = "MOUSE"


class BotCtl(Ctl):
    """PVP에서 상대가 없을 때 쓰는 간단한 AI"""

    def __init__(self):
        super().__init__()
        self.present = True
        self.center = (V.W * 0.8, V.H * 0.5)
        self.target = self.center
        self.t_next = 0.0
        self.fire_cd = 1.5

    def update(self, now, dt, foe):
        W, H = V.W, V.H
        if now > self.t_next:
            self.target = (random.uniform(0.62, 0.93) * W, random.uniform(0.22, 0.85) * H)
            self.t_next = now + random.uniform(0.7, 1.6)
        cx, cy = self.center
        dx, dy = self.target[0] - cx, self.target[1] - cy
        d = math.hypot(dx, dy)
        if d > 1:
            st = min(d, 240 * V.s * dt)
            cx, cy = cx + dx / d * st, cy + dy / d * st
        self.center = (cx, cy)
        self.size = S(70)
        fx, fy = foe.center
        ang = math.atan2(fy - cy, fx - cx) + random.gauss(0, 0.05)
        self.dir = (math.cos(ang), math.sin(ang))
        self.tip = (cx + self.dir[0] * S(62), cy + self.dir[1] * S(62))
        self.pos = self.tip
        self.fire_edge = self.trigger = False
        self.reload_edge = self.switch_edge = False
        self.fire_cd -= dt
        if self.fire_cd <= 0 and foe.present:
            self.fire_edge = self.trigger = True
            self.fire_cd = random.uniform(0.45, 1.0)
        self.pose = "BOT"


# ===================== 무기 / 저장 데이터 =====================
WEAPONS = {
    # 권총류
    "pistol":  dict(name="PISTOL",   dmg=34,  rate=0.30, mag=12, reload=1.0, pellets=1, spread=0,  auto=False,
                   pierce=False, price=0,   pack=0,  packcost=0,   pvp=11,  pvp_spread=0.015, col=(220, 220, 220),  snd="shot"),
    "glock17": dict(name="GLOCK 17", dmg=28,  rate=0.22, mag=17, reload=1.2, pellets=1, spread=0,  auto=False,
                   pierce=False, price=450, pack=34, packcost=55,  pvp=9,   pvp_spread=0.012, col=(200, 200, 200), snd="shot"),
    "m1911":   dict(name="M1911", dmg=42,  rate=0.35, mag=7, reload=1.5, pellets=1, spread=0,  auto=False,
                   pierce=False, price=500, pack=14, packcost=65, pvp=13,  pvp_spread=0.008, col=(180, 160, 120), snd="shot"),
    "deagle":  dict(name="DESERT EAGLE", dmg=85, rate=0.55, mag=7, reload=2.0, pellets=1, spread=5, auto=False,
                   pierce=True, price=1200, pack=14, packcost=120, pvp=25, pvp_spread=0.02, col=(220, 180, 60), snd="shot"),
    # 기관단총 / PDW
    "smg":     dict(name="SMG",     dmg=15, rate=0.085, mag=30, reload=1.5, pellets=1, spread=18, auto=True,
                   pierce=False, price=300, pack=60, packcost=60, pvp=4.5, pvp_spread=0.05, col=(80, 220, 255), snd="smg"),
    "mp5":     dict(name="MP5", dmg=22, rate=0.07, mag=30, reload=1.6, pellets=1, spread=14, auto=True,
                   pierce=False, price=650, pack=60, packcost=70, pvp=5, pvp_spread=0.04, col=(100, 180, 255), snd="smg"),
    "ump45":   dict(name="UMP45", dmg=30, rate=0.10, mag=25, reload=1.8, pellets=1, spread=10, auto=True,
                   pierce=False, price=700, pack=50, packcost=75, pvp=6, pvp_spread=0.025, col=(140, 120, 200), snd="smg"),
    "mac10":   dict(name="MAC-10", dmg=18, rate=0.05, mag=30, reload=1.4, pellets=1, spread=22, auto=True,
                   pierce=False, price=550, pack=60, packcost=60, pvp=4, pvp_spread=0.07, col=(150, 150, 150), snd="smg"),
    "vector":  dict(name="VECTOR", dmg=24, rate=0.055, mag=25, reload=1.5, pellets=1, spread=10, auto=True,
                   pierce=False, price=800, pack=50, packcost=70, pvp=5.5, pvp_spread=0.03, col=(255, 100, 200), snd="smg"),
    "p90":     dict(name="P90", dmg=20, rate=0.065, mag=50, reload=2.2, pellets=1, spread=16, auto=True,
                   pierce=False, price=850, pack=100, packcost=80, pvp=4.5, pvp_spread=0.05, col=(255, 200, 100), snd="smg"),
    "mp7":     dict(name="MP7", dmg=18, rate=0.06, mag=40, reload=1.8, pellets=1, spread=12, auto=True,
                   pierce=True, price=950, pack=80, packcost=90, pvp=5, pvp_spread=0.03, col=(200, 150, 255), snd="smg"),
    # 돌격소총
    "rifle":   dict(name="RIFLE",   dmg=26, rate=0.13, mag=30, reload=1.8, pellets=1, spread=7,  auto=True,
                   pierce=False, price=550, pack=60, packcost=75, pvp=6.5, pvp_spread=0.025, col=(255, 180, 80), snd="smg"),
    "ak47":    dict(name="AK-47", dmg=38, rate=0.09, mag=30, reload=2.0, pellets=1, spread=12, auto=True,
                   pierce=False, price=900, pack=60, packcost=90, pvp=7, pvp_spread=0.03, col=(120, 100, 60), snd="smg"),
    "m4a1":    dict(name="M4A1", dmg=32, rate=0.085, mag=30, reload=1.8, pellets=1, spread=8, auto=True,
                   pierce=False, price=1100, pack=60, packcost=85, pvp=6, pvp_spread=0.02, col=(100, 140, 100), snd="smg"),
    "scar":    dict(name="SCAR-L", dmg=35, rate=0.095, mag=30, reload=2.0, pellets=1, spread=10, auto=True,
                   pierce=False, price=1200, pack=60, packcost=95, pvp=6.5, pvp_spread=0.025, col=(80, 160, 100), snd="smg"),
    "g36":     dict(name="G36C", dmg=30, rate=0.10, mag=30, reload=1.9, pellets=1, spread=11, auto=True,
                   pierce=False, price=1000, pack=60, packcost=85, pvp=6, pvp_spread=0.028, col=(120, 160, 90), snd="smg"),
    "aug":     dict(name="AUG", dmg=34, rate=0.09, mag=30, reload=2.0, pellets=1, spread=9, auto=True,
                   pierce=False, price=1100, pack=60, packcost=90, pvp=6.2, pvp_spread=0.022, col=(90, 150, 110), snd="smg"),
    "m249":    dict(name="M249", dmg=28, rate=0.075, mag=100, reload=3.5, pellets=1, spread=20, auto=True,
                   pierce=False, price=1600, pack=200, packcost=150, pvp=5, pvp_spread=0.06, col=(100, 100, 80), snd="smg"),
    # 샷건
    "shotgun": dict(name="SHOTGUN", dmg=14, rate=0.80, mag=6, reload=2.0, pellets=8, spread=100, auto=False,
                   pierce=False, price=500, pack=12, packcost=80, pvp=4, pvp_spread=0.20, col=(80, 150, 255), snd="shotgun"),
    "rem870":  dict(name="REM 870", dmg=16, rate=0.75, mag=6, reload=2.2, pellets=10, spread=110, auto=False,
                   pierce=False, price=750, pack=12, packcost=90, pvp=5, pvp_spread=0.22, col=(80, 100, 220), snd="shotgun"),
    "m1014":   dict(name="M1014", dmg=18, rate=0.45, mag=7, reload=2.5, pellets=9, spread=95, auto=False,
                   pierce=False, price=900, pack=14, packcost=100, pvp=6, pvp_spread=0.18, col=(60, 120, 255), snd="shotgun"),
    # 저격소총
    "sniper":  dict(name="SNIPER",  dmg=140, rate=1.10, mag=5, reload=2.2, pellets=1, spread=0, auto=False,
                   pierce=True, price=800, pack=10, packcost=100, pvp=42, pvp_spread=0.0, col=(120, 255, 120), snd="sniper"),
    "m24":     dict(name="M24", dmg=160, rate=1.2, mag=5, reload=2.5, pellets=1, spread=0, auto=False,
                   pierce=True, price=1400, pack=10, packcost=130, pvp=40, pvp_spread=0.0, col=(100, 200, 100), snd="sniper"),
    "awp":     dict(name="AWP", dmg=200, rate=1.5, mag=5, reload=2.8, pellets=1, spread=0, auto=False,
                   pierce=True, price=1800, pack=10, packcost=150, pvp=50, pvp_spread=0.0, col=(0, 255, 180), snd="sniper"),
    # 로켓 / 폭발물
    "rpg7":    dict(name="RPG-7", dmg=500, rate=1.5, mag=1, reload=3.0, pellets=1, spread=0, auto=False,
                   pierce=True, price=2500, pack=2, packcost=300, pvp=0, pvp_spread=0.15, col=(255, 80, 60), snd="boom"),
    "grenade": dict(name="GRENADE", dmg=170, rate=0.9, mag=1, reload=0, pellets=1, spread=0, auto=False,
                   pierce=False, price=60, pack=1, packcost=60, pvp=0, pvp_spread=0, col=(60, 160, 255), snd="shot"),
}

# ===================== 양손 아킴보 무기 (실총 모델 기반 듀얼) =====================
# 각 손이 독립적으로 "탕 탕" 발사. 양손 모두 "총 모집" (검지 펴기, 나머지 접기) 상태여야 아킴보 발사 가능.
DUAL_WEAPONS = {
    "dual_pistol":   dict(name="DUAL PISTOL",   base="pistol",  dmg=34,  rate=0.22, mag=12, reload=1.0, pellets=1, spread=2,  auto=False, pierce=False, price=800,  pack=24, packcost=100, pvp=15,  pvp_spread=0.012, col=(220, 220, 100), snd="shot"),
    "dual_glock17":  dict(name="DUAL GLOCK 17", base="glock17", dmg=28,  rate=0.16, mag=17, reload=1.2, pellets=1, spread=3,  auto=False, pierce=False, price=900,  pack=34, packcost=120, pvp=13,  pvp_spread=0.010, col=(180, 220, 180), snd="shot"),
    "dual_m1911":    dict(name="DUAL M1911",    base="m1911",   dmg=42,  rate=0.25, mag=7,  reload=1.5, pellets=1, spread=2,  auto=False, pierce=False, price=1000, pack=14, packcost=140, pvp=18,  pvp_spread=0.008, col=(160, 140, 100), snd="shot"),
    "dual_deagle":   dict(name="DUAL DESERT EAGLE", base="deagle", dmg=85, rate=0.40, mag=7, reload=2.0, pellets=1, spread=6,  auto=False, pierce=True,  price=2200, pack=14, packcost=240, pvp=45,  pvp_spread=0.018, col=(200, 140, 60), snd="shot"),
    "dual_smg":      dict(name="DUAL SMG",      base="smg",     dmg=15,  rate=0.06, mag=30, reload=1.5, pellets=1, spread=25, auto=True,  pierce=False, price=1200, pack=120, packcost=140, pvp=8,   pvp_spread=0.07, col=(100, 200, 255), snd="smg"),
    "dual_mp5":      dict(name="DUAL MP5",      base="mp5",     dmg=22,  rate=0.05, mag=30, reload=1.6, pellets=1, spread=18, auto=True,  pierce=False, price=1400, pack=120, packcost=160, pvp=10,  pvp_spread=0.06, col=(100, 180, 255), snd="smg"),
    "dual_ump45":    dict(name="DUAL UMP45",     base="ump45",   dmg=30,  rate=0.07, mag=25, reload=1.8, pellets=1, spread=14, auto=True,  pierce=False, price=1500, pack=100, packcost=180, pvp=12,  pvp_spread=0.04, col=(140, 100, 200), snd="smg"),
}
GUNS = ["pistol", "glock17", "m1911", "deagle", "smg", "mp5", "ump45", "mac10", "vector", "p90", "mp7",
        "rifle", "ak47", "m4a1", "scar", "g36", "aug", "m249",
        "shotgun", "rem870", "m1014",
        "sniper", "m24", "awp"]
DUAL_GUNS = list(DUAL_WEAPONS.keys())
# 듀얼 무기를 주 무장 딕셔너리에도 등록 (Arsenal.w 조회용)
WEAPONS.update(DUAL_WEAPONS)
ORDER = GUNS + DUAL_GUNS + ["grenade"]
ITEMS = {
    "medkit": dict(name="MEDKIT", price=50, desc="Heal 50 HP  (key H / hold on HUD)"),
    "armor": dict(name="ARMOR", price=80, desc="+50 armor, absorbs 50% damage  (key A)"),
    "grenade": dict(name="GRENADE", price=60, desc="Area blast, throw at the crosshair"),
}
DEFAULT_SAVE = {
    "coins": 150, "owned": ["pistol"], "equipped": "pistol",
    "ammo": {"smg": 0, "rifle": 0, "shotgun": 0, "sniper": 0},
    "items": {"medkit": 1, "armor": 0, "grenade": 2},
    "best": {"pve_wave": 0, "pve_score": 0, "range": 0, "pvp_matches": 0},
    "settings": {"difficulty": 1, "sound": True, "tutorial_done": False, "trig": None},
    "kills": 0,
}


class Save:
    def __init__(self):
        self.d = json.loads(json.dumps(DEFAULT_SAVE))
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(self.d.get(k), dict):
                    self.d[k].update(v)
                else:
                    self.d[k] = v
        except Exception:
            pass
        if self.d["equipped"] not in self.d["owned"]:
            self.d["equipped"] = "pistol"
        if "pistol" not in self.d["owned"]:
            self.d["owned"].insert(0, "pistol")

    def write(self):
        try:
            tmp = SAVE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.d, f, indent=1)
            os.replace(tmp, SAVE_PATH)
        except Exception:
            pass


class Arsenal:
    """탄창/예비탄/장전/발사 간격 관리 (아킴보 지원)"""

    def __init__(self, guns, reserve, infinite=False, grenades=0, equipped=None, allow_grenade=False):
        self.guns = list(guns) or ["pistol"]
        self.infinite = infinite
        self.grenades = grenades
        self.allow_grenade = allow_grenade
        self.mag, self.res = {}, {}
        for g in self.guns:
            m = WEAPONS[g]["mag"]
            if infinite or g == "pistol":
                self.res[g], self.mag[g] = INF, m
            else:
                have = int(reserve.get(g, 0))
                take = min(m, have)
                self.mag[g], self.res[g] = take, have - take
        self.cur = equipped if equipped in self.guns else self.guns[0]
        self.dual = False           # 양손 아킴보 모드
        self.cur_l = self.cur       # 좌수 총
        self.cur_r = self.cur       # 우수 총
        self.last_l = -9.0
        self.last_r = -9.0
        self.reload_end = None
        self.reload_start = 0.0
        self.reload_side = None     # 'l', 'r', 또는 None

    @property
    def w(self):
        return WEAPONS[self.cur]

    def w_l(self):
        return WEAPONS[self.cur_l]

    def w_r(self):
        return WEAPONS[self.cur_r]

    def slots(self):
        return self.guns + (["grenade"] if self.allow_grenade else [])

    def select(self, name):
        if name == "grenade":
            if not self.allow_grenade:
                return False
        elif name not in self.guns:
            return False
        if name != self.cur:
            self.cur = name
            self.cur_l = name
            self.cur_r = name
            self.reload_end = None
        return True

    def set_dual(self, enable):
        self.dual = bool(enable)
        if self.dual:
            # 아킴보 모드 진입 시 현재 무기를 양손에 복제
            self.cur_l = self.cur
            self.cur_r = self.cur

    def cycle(self, d=1):
        order = self.guns + (["grenade"] if self.allow_grenade and self.grenades > 0 else [])
        if self.cur not in order:
            self.select(order[0])
            return
        self.select(order[(order.index(self.cur) + d) % len(order)])

    def reloading(self):
        return self.reload_end is not None

    def reload_frac(self, now):
        if self.reload_end is None:
            return 0.0
        return clamp((now - self.reload_start) / max(0.01, self.reload_end - self.reload_start), 0, 1)

    def start_reload(self, now, side=None):
        c = self.cur_l if side == "l" else (self.cur_r if side == "r" else self.cur)
        if c == "grenade" or self.reloading():
            return False
        if self.mag[c] >= WEAPONS[c]["mag"] or self.res[c] <= 0:
            return False
        self.reload_start = now
        self.reload_end = now + WEAPONS[c]["reload"]
        self.reload_side = side
        return True

    def update(self, now):
        if self.reload_end is not None and now >= self.reload_end:
            c = self.cur_l if self.reload_side == "l" else (self.cur_r if self.reload_side == "r" else self.cur)
            need = WEAPONS[c]["mag"] - self.mag[c]
            take = min(need, self.res[c])
            self.mag[c] += take
            if self.res[c] < INF // 2:
                self.res[c] -= take
            self.reload_end = None
            self.reload_side = None
            return True
        return False

    def shoot(self, now, side="both"):
        """양손 아킴보 발사: side='l' 좌수, 'r' 우수, 'both' 양손"""
        results = {}
        for s in (["l", "r"] if side == "both" else [side]):
            c = self.cur_l if s == "l" else self.cur_r
            last = self.last_l if s == "l" else self.last_r
            w = WEAPONS[c]
            if self.reloading():
                results[s] = "reloading"
                continue
            if now - last < w["rate"]:
                results[s] = "busy"
                continue
            if c == "grenade":
                if self.grenades <= 0:
                    results[s] = "empty"
                else:
                    self.grenades -= 1
                    if s == "l":
                        self.last_l = now
                    else:
                        self.last_r = now
                    results[s] = "ok"
                continue
            if self.mag[c] <= 0:
                if self.start_reload(now, side=s):
                    results[s] = "reload"
                else:
                    results[s] = "empty"
                continue
            self.mag[c] -= 1
            if s == "l":
                self.last_l = now
            else:
                self.last_r = now
            results[s] = "ok"
        return results

    def ammo_text(self):
        c = self.cur
        if c == "grenade":
            return "x%d" % self.grenades
        r = self.res[c]
        return "%d / %s" % (self.mag[c], "INF" if r >= INF // 2 else str(r))

    def ammo_text_lr(self):
        """양손 탄약 텍스트"""
        c_l, c_r = self.cur_l, self.cur_r
        def fmt(g):
            if g == "grenade":
                return "x%d" % self.grenades
            r = self.res[g]
            return "%d/%s" % (self.mag[g], "INF" if r >= INF // 2 else str(r))
        return fmt(c_l), fmt(c_r)

    def totals(self):
        return {g: self.mag[g] + self.res[g] for g in self.guns if self.res[g] < INF // 2}


class Dwell:
    """HUD 버튼을 일정 시간 가리키면 발동"""

    def __init__(self):
        self.key, self.t, self.done = None, 0.0, False

    def update(self, hover, dt):
        if hover != self.key:
            self.key, self.t, self.done = hover, 0.0, False
        if hover is None or self.done:
            return None
        self.t += dt
        if self.t >= DWELL_TIME:
            self.done = True
            return hover
        return None

    def prog(self, key):
        if key != self.key:
            return 0.0
        return 1.0 if self.done else clamp(self.t / DWELL_TIME, 0, 1)


def seg_circle(p0, p1, c, r):
    """선분(p0-p1)과 원(c, r)이 겹치는지"""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else clamp(((c[0] - p0[0]) * dx + (c[1] - p0[1]) * dy) / l2, 0, 1)
    return math.hypot(p0[0] + dx * t - c[0], p0[1] + dy * t - c[1]) <= r


# ===================== 게임 모드 공통 =====================
class Mode:
    name = "mode"
    cursor = True

    def __init__(self, g):
        self.g = g

    def leave(self):
        pass

    def update(self, dt, now):
        pass

    def draw(self, bg, now):
        return bg.copy()


class PlayMode(Mode):
    """PVE / 사격장 공통: HUD 버튼, 조준선, 무기 입력"""
    cursor = False

    def __init__(self, g):
        super().__init__(g)
        self.dwell = Dwell()
        self.btns = {}
        self.ar = None

    def menu_rect(self):
        return (V.W - S(124), S(12), V.W - S(12), S(52))

    def layout(self):
        self.btns = {"menu": (self.menu_rect(), "MENU", "")}

    def hud_hit(self, pos):
        return any(inside(b[0], pos) for b in self.btns.values())

    def run_dwell(self, dt, ctl):
        hov = None
        if ctl.present:
            for k, b in self.btns.items():
                if inside(b[0], ctl.pos):
                    hov = k
                    break
        return self.dwell.update(hov, dt)

    def weapon_inputs(self, ctl, now):
        ar, g = self.ar, self.g
        if ar.update(now):
            g.sfx.play("reload")
        if ctl.switch_edge or g.take("cycle"):
            ar.cycle(1)
            g.sfx.play("ui")
        if ctl.reload_edge or g.take("reload"):
            if ar.start_reload(now):
                g.sfx.play("reload")
        for i, wn in enumerate(ORDER):
            if g.take("w%d" % (i + 1)):
                if ar.select(wn):
                    g.sfx.play("ui")

    def draw_weapon_hud(self, img, now, y_text):
        ar = self.ar
        w = ar.w
        text(img, w["name"], V.W // 2, y_text - S(26), 0.8, w["col"], 2, "c")
        txt = "RELOADING" if ar.reloading() else ar.ammo_text()
        text(img, txt, V.W // 2, y_text, 0.85, (255, 255, 255) if not ar.reloading() else (0, 200, 255), 2, "c")
        if ar.reloading():
            bar(img, V.W // 2 - S(80), y_text + S(8), S(160), S(8), ar.reload_frac(now), (0, 200, 255))

    def draw_cross(self, img, ctl, now):
        if not ctl.present:
            if int(now * 2) % 2 == 0:
                text(img, "SHOW YOUR HAND  (gun pose)  -  or press V for mouse", V.W // 2, V.H // 2, 0.8, (0, 255, 255), 2, "c")
            return
        ar, w = self.ar, self.ar.w
        r = S(16) + int(S(w["spread"]) * 0.35)
        col = (0, 200, 255) if ar.reloading() else (255, 255, 255)
        crosshair(img, ctl.pos, r, col, T(2))
        if ar.reloading():
            cv2.ellipse(img, P2(ctl.pos), (r + S(8), r + S(8)), 0, -90, -90 + int(360 * ar.reload_frac(now)),
                        (0, 200, 255), T(3), cv2.LINE_AA)
        if ctl.palm_prog > 0 and not ar.reloading():
            cv2.ellipse(img, P2(ctl.pos), (r + S(14), r + S(14)), 0, -90, -90 + int(360 * ctl.palm_prog),
                        (0, 255, 0), T(3), cv2.LINE_AA)

    def draw_menu_btn(self, img, ctl):
        r, label, _ = self.btns["menu"]
        hov = ctl.present and inside(r, ctl.pos)
        btn_draw(img, r, label, hov, False, (70, 40, 40), self.dwell.prog("menu"), 0.6)


# ===================== 메뉴 =====================
class Menu(Mode):
    name = "menu"

    def items(self):
        d = DIFFS[self.g.save.d["settings"]["difficulty"]]
        cam_label = "CAMERA: %d" % self.g.cam_index
        return [("PVE   ZOMBIES", "pve"), ("PVP   DUEL", "pvp"), ("SHOOTING RANGE", "range"),
                ("INVENTORY / SHOP", "inv"), ("TUTORIAL", "tutorial"),
                ("DIFFICULTY: " + d["name"], "diff"), ("CAMERA: %d" % self.g.cam_index, "cam"),
                ("QUIT", "quit")]

    def rects(self):
        bw, bh, gap = S(430), S(50), S(10)
        n = len(self.items())
        total = n * bh + (n - 1) * gap
        top = max(S(140), int(V.H * 0.5 - total / 2 + S(10)))
        x0 = V.W // 2 - bw // 2
        return [(x0, top + i * (bh + gap), x0 + bw, top + i * (bh + gap) + bh) for i in range(n)]

    def update(self, dt, now):
        ctl = self.g.ptr()
        if ctl.present and ctl.fire_edge:
            for r, (_, key) in zip(self.rects(), self.items()):
                if inside(r, ctl.pos):
                    self.g.sfx.play("ui")
                    if key == "diff":
                        st = self.g.save.d["settings"]
                        st["difficulty"] = (st["difficulty"] + 1) % len(DIFFS)
                        self.g.save.write()
                    elif key == "cam":
                        self.g.cam_index = (self.g.cam_index + 1) % 6
                        self.g.toast("CAMERA: %d" % self.g.cam_index, 1.2)
                    else:
                        self.g.go(key)
                    return

    def draw(self, bg, now):
        g = self.g
        img = cv2.convertScaleAbs(bg, alpha=0.42)
        text(img, "GESTURE GUN", V.W // 2, S(86), 2.2, (0, 220, 255), 3, "c", FONT_B)
        text(img, "finger-gun shooter", V.W // 2, S(118), 0.7, (210, 210, 210), 1, "c")
        ctl = g.ptr()
        for r, (label, key) in zip(self.rects(), self.items()):
            col = (80, 60, 30) if key != "diff" else (60, 60, 90)
            btn_draw(img, r, label, ctl.present and inside(r, ctl.pos), False, col, 0, 0.8)
        if not g.save.d["settings"].get("tutorial_done") and int(now * 2) % 2 == 0:
            for r, (_, key) in zip(self.rects(), self.items()):
                if key == "tutorial":
                    text(img, "< START HERE", r[2] + S(14), (r[1] + r[3]) // 2 + S(8), 0.7, (0, 255, 255), 2)
        d = g.save.d
        text(img, "$ %d" % d["coins"], V.W - S(20), S(40), 0.9, (0, 215, 255), 2, "r")
        text(img, "BEST  wave %d  |  score %d  |  range %d  |  kills %d" % (
            d["best"]["pve_wave"], d["best"]["pve_score"], d["best"]["range"], d["kills"]),
             V.W - S(20), S(66), 0.5, (220, 220, 220), 1, "r")
        lines = ["GUN POSE (index up) = aim      THUMB DOWN = fire",
                 "OPEN PALM = reload      PEACE SIGN = switch weapon      FIST = guard",
                 "Aim at a button and fire to select.   Keys: SPACE fire, R reload, TAB switch, F fullscreen, ESC back"]
        for i, ln in enumerate(lines):
            text(img, ln, V.W // 2, V.H - S(62) + i * S(22), 0.48, (230, 230, 230), 1, "c")
        if not ctl.present:
            if int(now * 2) % 2 == 0:
                text(img, "SHOW YOUR HAND TO THE CAMERA  (or press V for mouse)", V.W // 2, S(150), 0.7, (0, 255, 255), 2, "c")
        g.draw_hand(img, g.hand_main if not g.mouse_mode else None)
        g.draw_cursor(img, ctl)
        return img


# ===================== PVE : 좀비 =====================
ZT = {
    "walker": dict(hp=70, spd=0.070, dmg=8, h=1.00, skin=(80, 170, 90), cloth=(120, 90, 60), coin=5, score=10),
    "runner": dict(hp=40, spd=0.160, dmg=6, h=0.88, skin=(110, 190, 150), cloth=(60, 60, 170), coin=7, score=15),
    "tank": dict(hp=280, spd=0.040, dmg=18, h=1.35, skin=(60, 120, 70), cloth=(55, 55, 55), coin=25, score=50),
    "boss": dict(hp=1400, spd=0.028, dmg=30, h=1.70, skin=(70, 70, 200), cloth=(30, 30, 90), coin=150, score=300),
}


class Zombie:
    def __init__(self, kind, wave, hp_mult=1.0):
        t = ZT[kind]
        self.kind = kind
        self.lane = random.uniform(0.12, 0.88)
        self.z = 0.0
        self.max = t["hp"] * (1 + 0.06 * (wave - 1)) * hp_mult
        self.hp = self.max
        self.spd = t["spd"] * random.uniform(0.85, 1.2) * (1 + 0.02 * wave)
        self.phase = random.uniform(0, 6.28)
        self.hurt = 0.0
        self.bite = 0.3


def zgeom(zb):
    z = zb.z
    sc = 0.18 + 0.95 * z
    h = S(300) * sc * ZT[zb.kind]["h"]
    x = V.W * (0.5 + (zb.lane - 0.5) * (0.35 + 0.85 * z))
    yf = V.H * (0.40 + 0.52 * z)
    return x, yf, h


def draw_zombie(img, zb, now):
    t = ZT[zb.kind]
    x, yf, h = zgeom(zb)
    if x < -h or x > V.W + h or yf - h > V.H:
        return
    fog = 0.55 + 0.45 * zb.z

    def col(c):
        r = [v * fog for v in c]
        if zb.hurt > 0:
            k = min(1.0, zb.hurt * 5)
            r = [v + (255 - v) * k for v in r]
        return C(r)

    skin, cloth = col(t["skin"]), col(t["cloth"])
    dark = col((35, 30, 30))
    sw = math.sin(now * (4 + zb.spd * 20) + zb.phase)
    lw = max(2, int(h * 0.13))
    for sg in (-1, 1):
        lx = x + sg * h * 0.09
        cv2.line(img, (int(lx), int(yf - h * 0.30)), (int(lx + sw * sg * h * 0.05), int(yf)), dark, lw)
    cv2.rectangle(img, (int(x - h * 0.19), int(yf - h * 0.72)), (int(x + h * 0.19), int(yf - h * 0.30)), cloth, -1)
    if zb.kind in ("tank", "boss"):
        cv2.rectangle(img, (int(x - h * 0.19), int(yf - h * 0.72)), (int(x + h * 0.19), int(yf - h * 0.55)), col((120, 120, 130)), -1)
    aw = max(2, int(h * 0.085))
    for sg in (-1, 1):
        sx, sy = x + sg * h * 0.19, yf - h * 0.68
        ex, ey = x + sg * h * 0.30 + sw * h * 0.02, yf - h * 0.50 + sw * sg * h * 0.03
        cv2.line(img, (int(sx), int(sy)), (int(ex), int(ey)), skin, aw)
        cv2.circle(img, (int(ex), int(ey)), max(2, int(h * 0.05)), skin, -1)
    hx, hy, hr = x + sw * h * 0.015, yf - h * 0.84, h * 0.125
    cv2.circle(img, (int(hx), int(hy)), max(3, int(hr)), skin, -1, cv2.LINE_AA)
    er = max(1, int(hr * 0.2))
    for sg in (-1, 1):
        cv2.circle(img, (int(hx + sg * hr * 0.4), int(hy - hr * 0.1)), er, (20, 20, 255), -1)
    cv2.line(img, (int(hx - hr * 0.4), int(hy + hr * 0.45)), (int(hx + hr * 0.4), int(hy + hr * 0.45)), dark, max(1, int(hr * 0.12)))
    if zb.kind == "boss":
        for sg in (-1, 1):
            cv2.line(img, (int(hx + sg * hr * 0.6), int(hy - hr * 0.7)), (int(hx + sg * hr * 0.9), int(hy - hr * 1.5)),
                     (30, 30, 230), max(2, int(hr * 0.22)))
    if zb.hp < zb.max:
        bw = int(h * 0.4)
        bar(img, int(x - bw / 2), int(yf - h * 1.04), bw, max(3, int(h * 0.035)), zb.hp / zb.max,
            (60, 60, 255) if zb.kind != "boss" else (0, 140, 255), (30, 30, 30), (200, 200, 200))


class PvE(PlayMode):
    name = "pve"

    def __init__(self, g):
        super().__init__(g)
        sv = g.save.d
        self.diff = DIFFS[clamp(int(sv["settings"]["difficulty"]), 0, len(DIFFS) - 1)]
        self.items = dict(sv["items"])
        # 양손 아킴보 무기 포함
        owned_guns = [w for w in GUNS if w in sv["owned"]] + [w for w in DUAL_GUNS if w in sv["owned"]]
        self.ar = Arsenal(owned_guns, sv["ammo"], False, self.items.get("grenade", 0),
                          sv["equipped"], allow_grenade=True)
        self.hp, self.armor = 100.0, 0.0
        self.wave = 0
        self.zs, self.queue, self.crates, self.nades = [], [], [], []
        self.spawn_t = 0.0
        self.score = self.kills = self.earned = 0
        self.state = "READY"
        self.t_state = g.now + 3.0
        self.last_count = 4
        self.banner = ("", 0.0)
        self.break_until = 0.0
        self.finished = False
        self.hit_marker = 0.0
        self.new_best = False
        self.layout()

    # ---------- 레이아웃 ----------
    def layout(self):
        W, H = V.W, V.H
        bw, bh, y = S(124), S(52), V.H - S(52) - S(14)
        b = {"menu": (self.menu_rect(), "MENU", "")}
        x = S(14)
        b["medkit"] = ((x, y, x + bw, y + bh), "MEDKIT", "x%d [H]" % self.items.get("medkit", 0))
        x += bw + S(8)
        b["armor"] = ((x, y, x + bw, y + bh), "ARMOR", "x%d [A]" % self.items.get("armor", 0))
        sw = S(84)
        slots = self.ar.slots()
        x = W - S(14) - len(slots) * (sw + S(6)) + S(6)
        for wn in slots:
            n = self.ar.grenades if wn == "grenade" else None
            b["w:" + wn] = ((x, y, x + sw, y + bh), WEAPONS[wn]["name"][:7], ("x%d" % n) if n is not None else "")
            x += sw + S(6)
        self.btns = b

    # ---------- 게임 진행 ----------
    def start_wave(self, now):
        n = self.wave
        q = ["walker"] * (4 + 2 * n)
        if n >= 2:
            q += ["runner"] * n
        if n >= 4:
            q += ["tank"] * (n // 3)
        random.shuffle(q)
        if n % 5 == 0:
            q = ["boss"] + q[:max(4, len(q) // 2)]
        self.queue = q
        self.spawn_t = 1.2
        self.banner = ("BOSS WAVE %d" % n if n % 5 == 0 else "WAVE %d" % n, now + 2.5)
        self.g.sfx.play("go")

    def hurt_player(self, dmg, ctl):
        dmg *= self.diff["zdmg"]
        if ctl.guard:
            dmg *= 0.5
        ab = min(self.armor, dmg * 0.5)
        self.armor -= ab
        self.hp -= dmg - ab
        self.g.fx.hurt = 0.55
        self.g.fx.shake = max(self.g.fx.shake, 9)
        self.g.sfx.play("hurt")
        if self.hp <= 0 and self.state == "PLAY":
            self.hp = 0
            self.finish(over=True)

    def finish(self, over=False):
        if self.finished:
            return
        self.finished = True
        sv = self.g.save.d
        if over:
            self.state = "OVER"
        for gname, tot in self.ar.totals().items():
            sv["ammo"][gname] = tot
        self.items["grenade"] = self.ar.grenades
        sv["items"] = dict(self.items)
        sv["coins"] += self.earned
        sv["kills"] += self.kills
        b = sv["best"]
        if self.wave > b["pve_wave"]:
            b["pve_wave"] = self.wave
            self.new_best = True
        if self.score > b["pve_score"]:
            b["pve_score"] = self.score
        self.g.save.write()

    def leave(self):
        self.finish()

    def kill(self, zb, head):
        t = ZT[zb.kind]
        self.zs.remove(zb)
        self.kills += 1
        c = int(round((t["coin"] + (3 if head else 0)) * self.diff["coin"]))
        self.earned += c
        self.score += t["score"] * (2 if head else 1)
        x, yf, h = zgeom(zb)
        fx = self.g.fx
        fx.burst(x, yf - h * 0.5, (40, 40, 200), 18, 300, 0.6, 3)
        fx.burst(x, yf - h * 0.5, (60, 170, 70), 8, 200, 0.5, 3)
        fx.text(x, yf - h, "+$%d" % c, (0, 215, 255), 0.7)
        self.g.sfx.play("kill")

    def damage_zombie(self, zb, dmg, head, pierce=False):
        fx = self.g.fx
        dmg = int(dmg)
        zb.hp -= dmg
        zb.hurt = 0.18
        zb.z = max(0.0, zb.z - min(0.05, dmg * 0.0004))
        x, yf, h = zgeom(zb)
        y = yf - h * (0.84 if head else 0.5)
        fx.burst(x, y, (30, 30, 190), 6, 220, 0.4, 2)
        fx.text(x + random.uniform(-10, 10), y - h * 0.1, ("HEADSHOT -%d" if head else "-%d") % dmg,
                (60, 60, 255) if head else (80, 230, 255), 0.6)
        self.hit_marker = 0.15
        if zb.hp <= 0:
            self.kill(zb, head)
        else:
            self.g.sfx.play("hit")

    def hit_point(self, x, y, dmg, pierce):
        """한 점(탄환)을 판정. 상자 > 좀비 순"""
        for c in list(self.crates):
            if math.hypot(x - c[0], y - (c[1] - S(18))) < S(44):
                self.collect(c)
                return True
        hit = False
        for zb in sorted(self.zs, key=lambda z: -z.z):
            zx, yf, h = zgeom(zb)
            hx, hy, hr = zx, yf - h * 0.84, h * 0.15
            head = math.hypot(x - hx, y - hy) <= hr
            body = abs(x - zx) <= h * 0.23 and yf - h * 0.74 <= y <= yf
            if head or body:
                self.damage_zombie(zb, dmg * (2 if head else 1), head, pierce)
                hit = True
                if not pierce:
                    break
        return hit

    def collect(self, c):
        self.crates.remove(c)
        fx, r = self.g.fx, random.random()
        if r < 0.3:
            self.items["medkit"] += 1
            msg = "MEDKIT +1"
        elif r < 0.5:
            self.items["armor"] += 1
            msg = "ARMOR +1"
        elif r < 0.75:
            lim = [g for g in self.ar.guns if g != "pistol"]
            if lim:
                gn = random.choice(lim)
                self.ar.res[gn] += WEAPONS[gn]["pack"]
                msg = "%s AMMO +%d" % (WEAPONS[gn]["name"], WEAPONS[gn]["pack"])
            else:
                self.earned += 20
                msg = "+$20"
        else:
            self.ar.grenades += 1
            msg = "GRENADE +1"
        fx.text(c[0], c[1] - S(40), msg, (120, 255, 120), 0.8)
        fx.burst(c[0], c[1] - S(20), (120, 255, 120), 14, 220, 0.5, 3)
        self.g.sfx.play("coin")
        self.layout()

    def explode(self, x, y, now):
        fx = self.g.fx
        R = S(190)
        fx.burst(x, y, (40, 140, 255), 40, 420, 0.7, 4)
        fx.burst(x, y, (40, 40, 255), 20, 300, 0.6, 4)
        fx.ring(x, y, R, (60, 180, 255), 0.45)
        fx.shake = max(fx.shake, 20)
        fx.flash = 0.3
        self.g.sfx.play("boom")
        for zb in list(self.zs):
            zx, yf, h = zgeom(zb)
            d = math.hypot(zx - x, (yf - h * 0.4) - y)
            if d < R + h * 0.25:
                self.damage_zombie(zb, int(WEAPONS["grenade"]["dmg"] * (1 - 0.5 * min(1, d / (R + h * 0.25)))), False)

    def fire(self, ctl, now):
        ar, g = self.ar, self.g

        # ---------- 양손 아킴보 모드 ----------
        if ar.dual:
            # 탭 카운트에 따라 좌우 번갈아 발사 (탕-탕)
            side = "l" if ctl.tap_count % 2 == 1 else "r"
            results = ar.shoot(now, side=side)
            res = results.get(side, "busy")
            if res == "empty":
                g.sfx.play("empty")
                return
            if res == "reload":
                g.sfx.play("reload")
                return
            if res != "ok":
                return
            w = ar.w_l() if side == "l" else ar.w_r()
            pos = ctl.shot_pos()
            g.sfx.play(w["snd"])
            g.fx.shake = max(g.fx.shake, 3 + w["dmg"] / 40.0)
            g.fx.burst(pos[0], pos[1], (120, 230, 255), 5, 160, 0.15, 3, 0)
            for _ in range(w["pellets"]):
                a, rr = random.uniform(0, 6.283), math.sqrt(random.random()) * S(w["spread"])
                self.hit_point(pos[0] + math.cos(a) * rr, pos[1] + math.sin(a) * rr, w["dmg"], w["pierce"])
            return

        # ---------- 일반 단일 무장 ----------
        res = ar.shoot(now)
        if res == "empty":
            g.sfx.play("empty")
            return
        if res == "reload":
            g.sfx.play("reload")
            return
        if res != "ok":
            return
        w, pos = ar.w, ctl.shot_pos()
        g.sfx.play(w["snd"])
        g.fx.shake = max(g.fx.shake, 3 + w["dmg"] / 40.0)
        g.fx.burst(pos[0], pos[1], (120, 230, 255), 5, 160, 0.15, 3, 0)
        if ar.cur == "grenade":
            self.nades.append([pos[0], pos[1], now + 0.55])
            self.layout()
            return
        for _ in range(w["pellets"]):
            a, rr = random.uniform(0, 6.283), math.sqrt(random.random()) * S(w["spread"])
            self.hit_point(pos[0] + math.cos(a) * rr, pos[1] + math.sin(a) * rr, w["dmg"], w["pierce"])

    def melee_attack(self, ctl, now):
        """근접 공격: 손 앞 방향의 좀비를 때림 (콤보 보너스 적용)"""
        g = self.g
        g.sfx.play("melee")
        g.fx.shake = max(g.fx.shake, 6)
        g.fx.burst(ctl.pos[0], ctl.pos[1], (255, 100, 100), 12, 200, 0.4, 3, 0)
        # 콤보 보너스 데미지 계산
        combo = ctl.melee_combo
        bonus_mult = 1.0 + (combo - 1) * (MELEE_COMBO_BONUS - 1) / (MELEE_COMBO_MAX - 1) if combo > 1 else 1.0
        dmg = int(MELEE_DMG * bonus_mult)
        # 손 앞 방향에 있는 좀비 판정
        hit_any = False
        for zb in list(self.zs):
            zx, yf, h = zgeom(zb)
            dist = math.hypot(ctl.pos[0] - zx, ctl.pos[1] - (yf - h * 0.5))
            if dist < S(MELEE_RANGE):
                self.damage_zombie(zb, dmg, head=False)
                hit_any = True
        if hit_any:
            g.fx.text(ctl.pos[0], ctl.pos[1] - S(40), f"x{combo} COMBO" if combo > 1 else "MELEE",
                      (255, 100, 100), 0.8)
            g.fx.ring(ctl.pos[0], ctl.pos[1], S(MELEE_RANGE), (255, 80, 80), 0.4)
            # 콤보 보상 코인
            if combo >= 2:
                bonus = int(combo * 2)
                self.g.save.d["coins"] += bonus
                self.g.save.write()
                g.fx.text(ctl.pos[0], ctl.pos[1] - S(70), f"+${bonus} COMBO", (0, 255, 255), 0.9)
                g.sfx.play("coin")

    def use_item(self, key, ctl):
        fx = self.g.fx
        if key == "medkit" and self.items["medkit"] > 0 and self.hp < 100:
            self.items["medkit"] -= 1
            self.hp = min(100, self.hp + 50)
            fx.text(V.W // 2, V.H * 0.4, "+50 HP", (80, 255, 80), 1.0)
            self.g.sfx.play("coin")
        elif key == "armor" and self.items["armor"] > 0 and self.armor < 100:
            self.items["armor"] -= 1
            self.armor = min(100, self.armor + 50)
            fx.text(V.W // 2, V.H * 0.4, "+50 ARMOR", (255, 200, 80), 1.0)
            self.g.sfx.play("coin")
        self.layout()

    # ---------- 업데이트 ----------
    def update(self, dt, now):
        g = self.g
        ctl = g.ptr()
        self.layout()
        self.hit_marker = max(0.0, self.hit_marker - dt)
        act = self.run_dwell(dt, ctl)
        if act == "menu":
            g.go("menu")
            return
        if act in ("medkit", "armor"):
            self.use_item(act, ctl)
        elif act and act.startswith("w:"):
            if self.ar.select(act[2:]):
                g.sfx.play("ui")
        if g.take("medkit"):
            self.use_item("medkit", ctl)
        if g.take("armor"):
            self.use_item("armor", ctl)

        if self.state == "READY":
            left = self.t_state - now
            n = int(math.ceil(left))
            if n != self.last_count and n >= 1:
                self.last_count = n
                g.sfx.play("beep")
            if left <= 0:
                self.state = "PLAY"
                self.wave = 1
                self.start_wave(now)
            self.weapon_inputs(ctl, now)
            return
        if self.state == "OVER":
            self.over_buttons(ctl)
            return

        self.weapon_inputs(ctl, now)
        if ctl.present:
            ar = self.ar
            want = ctl.trigger if ar.w["auto"] else ctl.fire_edge
            if want and not self.hud_hit(ctl.pos):
                self.fire(ctl, now)
            # 근접 공격 (복싱 잽)
            if ctl.melee_edge and not self.hud_hit(ctl.pos):
                self.melee_attack(ctl, now)

        # 수류탄
        for n in list(self.nades):
            if now >= n[2]:
                self.nades.remove(n)
                self.explode(n[0], n[1], now)

        # 좀비 이동 / 공격
        for zb in list(self.zs):
            zb.hurt = max(0.0, zb.hurt - dt)
            if zb.z < 1.0:
                zb.z = min(1.0, zb.z + zb.spd * dt)
            else:
                zb.bite -= dt
                if zb.bite <= 0:
                    zb.bite = 0.9
                    self.hurt_player(ZT[zb.kind]["dmg"], ctl)
                    if self.state == "OVER":
                        return

        # 상자 수명
        for c in list(self.crates):
            c[2] -= dt
            if c[2] <= 0:
                self.crates.remove(c)

        # 스폰 / 웨이브
        if self.queue:
            self.spawn_t -= dt
            if self.spawn_t <= 0:
                self.zs.append(Zombie(self.queue.pop(), self.wave, self.diff["zhp"]))
                self.spawn_t = max(0.45, 2.1 - 0.12 * self.wave) * self.diff["spawn"] * random.uniform(0.7, 1.3)
        elif not self.zs and self.break_until == 0.0:
            bonus = int(10 * self.wave * self.diff["coin"])
            self.earned += bonus
            self.score += 50 * self.wave
            self.hp = min(100, self.hp + 15)
            self.break_until = now + 4.0
            self.banner = ("WAVE %d CLEARED  +$%d" % (self.wave, bonus), now + 3.0)
            self.g.sfx.play("win")
            self.crates.append([random.uniform(0.2, 0.8) * V.W, V.H * random.uniform(0.62, 0.8), 14.0])
        elif self.break_until and now >= self.break_until:
            self.break_until = 0.0
            self.wave += 1
            self.start_wave(now)

    def over_buttons(self, ctl):
        if not (ctl.present and ctl.fire_edge):
            return
        a, b = self.over_rects()
        if inside(a, ctl.pos):
            self.g.go("pve")
        elif inside(b, ctl.pos):
            self.g.go("menu")

    def over_rects(self):
        cx, y, bw, bh = V.W // 2, int(V.H * 0.68), S(220), S(56)
        return (cx - bw - S(10), y, cx - S(10), y + bh), (cx + S(10), y, cx + bw + S(10), y + bh)

    # ---------- 그리기 ----------
    def draw(self, bg, now):
        g = self.g
        ctl = g.ptr()
        img = cv2.multiply(bg, g.ground_mul(), scale=1 / 255.0)
        for c in self.crates:
            x, y = int(c[0]), int(c[1])
            s = S(30)
            cv2.rectangle(img, (x - s, y - 2 * s), (x + s, y), (40, 110, 170), -1)
            cv2.rectangle(img, (x - s, y - 2 * s), (x + s, y), (20, 70, 120), T(2))
            cv2.line(img, (x - s, y - s), (x + s, y - s), (20, 70, 120), T(2))
            cv2.line(img, (x, y - 2 * s), (x, y), (20, 70, 120), T(2))
            if int(now * 3) % 2 == 0:
                cv2.circle(img, (x, y - s), s + S(8), (120, 255, 120), T(2), cv2.LINE_AA)
        for zb in sorted(self.zs, key=lambda z: z.z):
            draw_zombie(img, zb, now)
        for n in self.nades:
            k = 1 - (n[2] - now) / 0.55
            cv2.circle(img, P2(n[:2]), S(14), (40, 120, 40), -1, cv2.LINE_AA)
            cv2.circle(img, P2(n[:2]), int(S(40) * (1 - k) + S(14)), (60, 160, 255), T(2), cv2.LINE_AA)
        g.fx.draw(img)
        g.draw_hand(img, g.hand_main if not g.mouse_mode else None, only_small=True)
        self.draw_hud(img, ctl, now)
        self.draw_cross(img, ctl, now)
        if ctl.present and self.hit_marker > 0:
            x, y, d = int(ctl.pos[0]), int(ctl.pos[1]), S(26)
            for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                cv2.line(img, (x + dx * S(10), y + dy * S(10)), (x + dx * d, y + dy * d), (0, 0, 255), T(3), cv2.LINE_AA)
        if self.state == "READY":
            left = max(0, int(math.ceil(self.t_state - now)))
            text(img, "GET READY", V.W // 2, int(V.H * 0.28), 1.6, (0, 255, 255), 3, "c")
            text(img, str(left), V.W // 2, int(V.H * 0.42), 3.0, (255, 255, 255), 4, "c")
        elif self.state == "PLAY" and now < self.banner[1]:
            text(img, self.banner[0], V.W // 2, int(V.H * 0.28), 1.5, (0, 220, 255), 3, "c")
        if self.state == "OVER":
            self.draw_over(img, ctl)
        return img

    def draw_hud(self, img, ctl, now):
        W, H = V.W, V.H
        bar(img, S(16), S(16), S(300), S(24), self.hp / 100.0, (60, 60, 230) if self.hp > 30 else (40, 40, 255))
        text(img, "HP %d" % max(0, int(self.hp)), S(24), S(35), 0.6, (255, 255, 255), 2)
        if self.armor > 0:
            bar(img, S(16), S(46), S(300), S(10), self.armor / 100.0, (255, 180, 60))
        text(img, "WAVE %d" % max(1, self.wave), W // 2, S(36), 0.9, (0, 220, 255), 2, "c")
        text(img, "SCORE %d   KILLS %d   [%s]" % (self.score, self.kills, self.diff["name"]), W // 2, S(62), 0.55,
             (230, 230, 230), 1, "c")
        text(img, "$ %d" % (self.g.save.d["coins"] + self.earned), W - S(20), S(82), 0.8, (0, 215, 255), 2, "r")
        # 근접 공격 쿨다운 / 콤보 HUD
        ctl = self.g.ptr()
        if ctl and ctl.present:
            if ctl.melee_combo > 0:
                text(img, "MELEE x%d COMBO" % ctl.melee_combo, W // 2, S(100), 0.8, (255, 100, 100), 2, "c")
            elif not ctl.melee_ready:
                cool_left = max(0, int(math.ceil(ctl.melee_cool)))
                text(img, "MELEE %ds" % cool_left, W // 2, S(100), 0.8, (255, 200, 100), 2, "c")
            else:
                text(img, "MELEE READY", W // 2, S(100), 0.8, (100, 255, 100), 2, "c")
        self.draw_menu_btn(img, ctl)
        for k, (r, label, sub) in self.btns.items():
            if k == "menu":
                continue
            hov = ctl.present and inside(r, ctl.pos)
            sel = k == "w:" + self.ar.cur
            if k == "medkit":
                col, en = (40, 110, 40), self.items["medkit"] > 0
            elif k == "armor":
                col, en = (110, 80, 30), self.items["armor"] > 0
            else:
                col, en = (70, 70, 70), True
            btn_draw(img, r, label, hov, sel, col, self.dwell.prog(k), 0.5, en, sub or None)
        self.draw_weapon_hud(img, now, H - S(34))

    def draw_over(self, img, ctl):
        shade(img, 0, 0, V.W, V.H, (0, 0, 0), 0.6)
        text(img, "YOU DIED", V.W // 2, int(V.H * 0.22), 2.0, (60, 60, 255), 4, "c", FONT_B)
        lines = ["REACHED WAVE %d" % self.wave, "SCORE %d    KILLS %d" % (self.score, self.kills),
                 "COINS EARNED  +$%d" % self.earned]
        if self.new_best:
            lines.append("NEW BEST WAVE!")
        for i, ln in enumerate(lines):
            text(img, ln, V.W // 2, int(V.H * 0.34) + i * S(36), 0.85, (0, 255, 255) if i == 3 else (255, 255, 255), 2, "c")
        a, b = self.over_rects()
        btn_draw(img, a, "RETRY", ctl.present and inside(a, ctl.pos), False, (40, 100, 40), 0, 0.8)
        btn_draw(img, b, "MENU", ctl.present and inside(b, ctl.pos), False, (100, 60, 40), 0, 0.8)
        self.g.draw_cursor(img, ctl)


# ===================== 사격장 =====================
class Range(PlayMode):
    name = "range"
    DURATION = 60.0

    def __init__(self, g):
        super().__init__(g)
        sv = g.save.d
        self.ar = Arsenal([w for w in GUNS if w in sv["owned"]], {}, True, 0, sv["equipped"])
        self.state = "READY"
        self.t_state = g.now + 3.0
        self.last_count = 4
        self.targets = []
        self.spawn_t = 0.5
        self.score = self.shots = self.hits = self.streak = self.best_streak = 0
        self.t_end = 0.0
        self.earned = 0
        self.new_best = False
        self.finished = False
        self.layout()

    def spawn(self):
        W, H = V.W, V.H
        r = random.random()
        kind = "bull" if r < 0.62 else ("gold" if r < 0.82 else "civ")
        rad = {"bull": random.randint(44, 64), "gold": 30, "civ": 46}[kind]
        spd = random.choice([0, 0, 110, 170, 230, 330]) * (1.5 if kind == "gold" else 1) * random.choice([-1, 1])
        ttl = random.uniform(3.5, 6.0) if kind != "gold" else random.uniform(2.2, 3.2)
        self.targets.append(dict(kind=kind, x=random.uniform(0.12, 0.88) * W, y=random.uniform(0.30, 0.72) * H,
                                 r=S(rad), vx=S(spd), ttl=ttl, born=0.0, hit=None))

    def hit_point(self, x, y, now):
        """return (points, name) or None"""
        for t in reversed(self.targets):
            if t["hit"] is not None:
                continue
            d = math.hypot(x - t["x"], y - t["y"])
            if d <= t["r"]:
                t["hit"] = now
                k = d / t["r"]
                if t["kind"] == "bull":
                    return (100 if k < 0.22 else 50 if k < 0.55 else 20), "bull", t
                if t["kind"] == "gold":
                    return 200, "gold", t
                return -150, "civ", t
        return None

    def fire(self, ctl, now):
        ar, g = self.ar, self.g

        # ---------- 양손 아킴보 모드 ----------
        if ar.dual:
            side = "l" if ctl.tap_count % 2 == 1 else "r"
            results = ar.shoot(now, side=side)
            res = results.get(side, "busy")
            if res == "empty":
                g.sfx.play("empty")
                return
            if res == "reload":
                g.sfx.play("reload")
                return
            if res != "ok":
                return
            w = ar.w_l() if side == "l" else ar.w_r()
            pos = ctl.shot_pos()
            g.sfx.play(w["snd"])
            g.fx.shake = max(g.fx.shake, 2 + w["dmg"] / 50.0)
            self.shots += 1
            got, bad = 0, False
            for _ in range(w["pellets"]):
                a, rr = random.uniform(0, 6.283), math.sqrt(random.random()) * S(w["spread"])
                px, py = pos[0] + math.cos(a) * rr, pos[1] + math.sin(a) * rr
                h = self.hit_point(px, py, now)
                if h is None:
                    g.fx.burst(px, py, (200, 200, 200), 3, 120, 0.25, 2, 0)
                    continue
                pts, kind, t = h
                if pts < 0:
                    bad = True
                    self.score += pts
                    g.fx.text(t["x"], t["y"] - t["r"], "OOPS! %d" % pts, (60, 60, 255), 0.9)
                    g.sfx.play("hurt")
                else:
                    mult = 1 + 0.1 * min(self.streak, 20)
                    add = int(pts * mult)
                    self.score += add
                    got += 1
                    g.fx.text(t["x"], t["y"] - t["r"], "+%d" % add,
                              (0, 215, 255) if kind == "gold" else (255, 255, 255), 0.8)
                    g.fx.burst(t["x"], t["y"],
                               (0, 215, 255) if kind == "gold" else (60, 60, 255), 12, 260, 0.4, 3)
                    g.sfx.play("hit")
            if got and not bad:
                self.hits += 1
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
            else:
                self.streak = 0
            self.score = max(0, self.score)
            return

        # ---------- 일반 단일 무장 ----------
        res = ar.shoot(now)
        if res == "empty":
            g.sfx.play("empty")
            return
        if res == "reload":
            g.sfx.play("reload")
            return
        if res != "ok":
            return
        w, pos = ar.w, ctl.shot_pos()
        g.sfx.play(w["snd"])
        g.fx.shake = max(g.fx.shake, 2 + w["dmg"] / 50.0)
        self.shots += 1
        got, bad = 0, False
        for _ in range(w["pellets"]):
            a, rr = random.uniform(0, 6.283), math.sqrt(random.random()) * S(w["spread"])
            px, py = pos[0] + math.cos(a) * rr, pos[1] + math.sin(a) * rr
            h = self.hit_point(px, py, now)
            if h is None:
                g.fx.burst(px, py, (200, 200, 200), 3, 120, 0.25, 2, 0)
                continue
            pts, kind, t = h
            if pts < 0:
                bad = True
                self.score += pts
                g.fx.text(t["x"], t["y"] - t["r"], "OOPS! %d" % pts, (60, 60, 255), 0.9)
                g.sfx.play("hurt")
            else:
                mult = 1 + 0.1 * min(self.streak, 20)
                add = int(pts * mult)
                self.score += add
                got += 1
                g.fx.text(t["x"], t["y"] - t["r"], "+%d" % add,
                          (0, 215, 255) if kind == "gold" else (255, 255, 255), 0.8)
                g.fx.burst(t["x"], t["y"],
                           (0, 215, 255) if kind == "gold" else (60, 60, 255), 12, 260, 0.4, 3)
                g.sfx.play("hit")
        if got and not bad:
            self.hits += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
        else:
            self.streak = 0
        self.score = max(0, self.score)

    def finish(self):
        if self.finished:
            return
        self.finished = True
        sv = self.g.save.d
        self.earned = self.score // 25
        sv["coins"] += self.earned
        if self.score > sv["best"]["range"]:
            sv["best"]["range"] = self.score
            self.new_best = True
        self.g.save.write()

    def leave(self):
        pass

    def grade(self):
        s = self.score
        return "S" if s >= 3500 else "A" if s >= 2500 else "B" if s >= 1500 else "C" if s >= 700 else "D"

    def update(self, dt, now):
        g = self.g
        ctl = g.ptr()
        self.btns = {"menu": (self.menu_rect(), "MENU", "")}
        if self.run_dwell(dt, ctl) == "menu":
            g.go("menu")
            return
        self.weapon_inputs(ctl, now)
        if self.state == "READY":
            left = self.t_state - now
            n = int(math.ceil(left))
            if n != self.last_count and n >= 1:
                self.last_count = n
                g.sfx.play("beep")
            if left <= 0:
                self.state = "PLAY"
                self.t_end = now + self.DURATION
                g.sfx.play("go")
            return
        if self.state == "OVER":
            if ctl.present and ctl.fire_edge:
                a, b = self.over_rects()
                if inside(a, ctl.pos):
                    g.go("range")
                elif inside(b, ctl.pos):
                    g.go("menu")
            return
        if now >= self.t_end:
            self.state = "OVER"
            self.finish()
            g.sfx.play("win")
            return
        if ctl.present:
            want = ctl.trigger if self.ar.w["auto"] else ctl.fire_edge
            if want and not self.hud_hit(ctl.pos):
                self.fire(ctl, now)
        for t in list(self.targets):
            t["born"] += dt
            if t["hit"] is None:
                t["x"] += t["vx"] * dt
                if t["x"] < t["r"] or t["x"] > V.W - t["r"]:
                    t["vx"] = -t["vx"]
                    t["x"] = clamp(t["x"], t["r"], V.W - t["r"])
                if t["born"] > t["ttl"]:
                    self.targets.remove(t)
            elif now - t["hit"] > 0.3:
                self.targets.remove(t)
        self.spawn_t -= dt
        if self.spawn_t <= 0 and len(self.targets) < 5:
            self.spawn()
            self.spawn_t = random.uniform(0.35, 0.85)

    def over_rects(self):
        cx, y, bw, bh = V.W // 2, int(V.H * 0.72), S(220), S(56)
        return (cx - bw - S(10), y, cx - S(10), y + bh), (cx + S(10), y, cx + bw + S(10), y + bh)

    def draw_target(self, img, t, now):
        x, y, r = int(t["x"]), int(t["y"]), t["r"]
        if t["hit"] is not None:
            k = clamp((now - t["hit"]) / 0.3, 0, 1)
            r = max(2, int(r * (1 - k)))
            y += int(S(40) * k)
        if t["kind"] == "bull":
            for rr, c in ((1.0, (240, 240, 240)), (0.78, (50, 50, 220)), (0.55, (240, 240, 240)), (0.34, (50, 50, 220)), (0.15, (30, 30, 30))):
                cv2.circle(img, (x, y), max(1, int(r * rr)), c, -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), r, (20, 20, 20), T(2), cv2.LINE_AA)
        elif t["kind"] == "gold":
            cv2.circle(img, (x, y), r, (0, 190, 255), -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), r, (0, 120, 200), T(3), cv2.LINE_AA)
            cv2.circle(img, (x, y), max(1, int(r * 0.45)), (0, 240, 255), -1, cv2.LINE_AA)
        else:
            cv2.circle(img, (x, y - int(r * 0.45)), max(2, int(r * 0.35)), (200, 140, 60), -1, cv2.LINE_AA)
            cv2.ellipse(img, (x, y + int(r * 0.5)), (max(2, int(r * 0.7)), max(2, int(r * 0.55))), 0, 180, 360,
                        (200, 140, 60), -1, cv2.LINE_AA)
            cv2.rectangle(img, (x - int(r * 0.7), y + int(r * 0.5)), (x + int(r * 0.7), y + int(r * 0.6)), (200, 140, 60), -1)
            if t["hit"] is None:
                text(img, "CIVILIAN", x, y - r - S(6), 0.4, (255, 200, 120), 1, "c")

    def draw(self, bg, now):
        g = self.g
        ctl = g.ptr()
        img = cv2.convertScaleAbs(bg, alpha=0.5)
        # 사격장 바닥 라인
        for i in range(1, 6):
            y = int(V.H * (0.78 + 0.04 * i * i / 5))
            cv2.line(img, (0, y), (V.W, y), (90, 90, 90), 1)
        for t in self.targets:
            self.draw_target(img, t, now)
        g.fx.draw(img)
        g.draw_hand(img, g.hand_main if not g.mouse_mode else None, only_small=True)
        W, H = V.W, V.H
        left = max(0.0, self.t_end - now) if self.state == "PLAY" else (self.DURATION if self.state == "READY" else 0.0)
        bar(img, W // 2 - S(150), S(14), S(300), S(14), left / self.DURATION, (0, 200, 255))
        text(img, "%d s" % int(math.ceil(left)), W // 2, S(46), 0.8, (255, 255, 255), 2, "c")
        text(img, "SCORE %d" % self.score, S(20), S(38), 1.0, (0, 220, 255), 2)
        acc = 100.0 * self.hits / self.shots if self.shots else 0.0
        text(img, "ACC %d%%   STREAK %d  x%.1f" % (acc, self.streak, 1 + 0.1 * min(self.streak, 20)), S(20), S(66), 0.55, (230, 230, 230), 1)
        self.draw_menu_btn(img, ctl)
        self.draw_weapon_hud(img, now, H - S(34))
        self.draw_cross(img, ctl, now)
        if self.state == "READY":
            text(img, "SHOOTING RANGE", W // 2, int(H * 0.2), 1.4, (0, 255, 255), 3, "c")
            text(img, "Hit targets, avoid civilians. Chain hits for a combo bonus.", W // 2, int(H * 0.27), 0.6, (230, 230, 230), 1, "c")
            text(img, str(max(0, int(math.ceil(self.t_state - now)))), W // 2, int(H * 0.45), 3.0, (255, 255, 255), 4, "c")
        if self.state == "OVER":
            shade(img, 0, 0, W, H, (0, 0, 0), 0.6)
            text(img, "TIME UP", W // 2, int(H * 0.2), 1.8, (0, 220, 255), 4, "c", FONT_B)
            text(img, self.grade(), W // 2, int(H * 0.40), 3.2, (0, 255, 255), 5, "c", FONT_B)
            text(img, "SCORE %d   ACC %d%%   BEST STREAK %d" % (self.score, acc, self.best_streak), W // 2, int(H * 0.5), 0.8, (255, 255, 255), 2, "c")
            text(img, "COINS +$%d%s" % (self.earned, "   NEW BEST!" if self.new_best else ""), W // 2, int(H * 0.58), 0.8, (0, 215, 255), 2, "c")
            a, b = self.over_rects()
            btn_draw(img, a, "RETRY", ctl.present and inside(a, ctl.pos), False, (40, 100, 40), 0, 0.8)
            btn_draw(img, b, "MENU", ctl.present and inside(b, ctl.pos), False, (100, 60, 40), 0, 0.8)
            g.draw_cursor(img, ctl)
        return img


# ===================== PVP =====================
PCOL = [(255, 170, 60), (70, 70, 255)]


class Player:
    def __init__(self, idx):
        self.idx = idx
        self.hp = 100.0
        self.ar = Arsenal(list(GUNS) + list(DUAL_GUNS), {}, True)
        self.ctl = None
        self.flash = 0.0
        self.col = PCOL[idx]


class PvP(Mode):
    name = "pvp"
    cursor = False

    def __init__(self, g):
        super().__init__(g)
        self.pl = [Player(0), Player(1)]
        self.bot = None
        self.use_bot = False
        self.state = "WAIT"
        self.t_state = 0.0
        self.t_wait = 0.0
        self.bullets = []
        self.wins = [0, 0]
        self.round = 1
        self.winner = None
        self.last_count = 4
        self.rewarded = False
        self.dwell = Dwell()

    def assign(self):
        g = self.g
        if g.mouse_mode:
            if self.bot is None:
                self.bot = BotCtl()
            self.pl[0].ctl, self.pl[1].ctl = g.mouse, self.bot
        elif self.use_bot:
            if self.bot is None:
                self.bot = BotCtl()
            self.pl[0].ctl, self.pl[1].ctl = g.hand_main, self.bot
        else:
            self.pl[0].ctl, self.pl[1].ctl = g.hand_lr[0], g.hand_lr[1]

    def cover(self, now):
        cx = V.W // 2
        cy = V.H * 0.52 + math.sin(now * 0.7) * V.H * 0.17
        return (cx - S(30), cy - S(100), cx + S(30), cy + S(100))

    def radius(self, p):
        return max(p.ctl.size * 0.85, S(46))

    def reset_round(self, now):
        for p in self.pl:
            p.hp = 100.0
            p.ar = Arsenal(GUNS, {}, True)
            p.flash = 0.0
        self.bullets = []
        self.state = "READY"
        self.t_state = now + 3.0
        self.last_count = 4

    def shoot(self, p, foe, now):
        ar, g = p.ar, self.g
        res = ar.shoot(now)
        if res == "empty":
            g.sfx.play("empty")
            return
        if res == "reload":
            g.sfx.play("reload")
            return
        if res != "ok":
            return
        w, c = ar.w, p.ctl
        ox, oy = c.tip
        base = math.atan2(c.dir[1], c.dir[0])
        for _ in range(w["pellets"]):
            a = base + random.uniform(-w["pvp_spread"], w["pvp_spread"])
            sp = S(1250)
            self.bullets.append([ox, oy, ox, oy, math.cos(a) * sp, math.sin(a) * sp, p.idx, w["pvp"], 1.4])
        g.fx.burst(ox, oy, p.col, 6, 200, 0.15, 3, 0)
        g.sfx.play(w["snd"])

    def damage(self, foe, shooter, dmg, x, y):
        if foe.ctl.guard:
            dmg *= 0.2
        foe.hp -= dmg
        foe.flash = 0.2
        fx = self.g.fx
        fx.burst(x, y, foe.col, 6, 220, 0.4, 3)
        fx.text(x, y - S(20), "-%.0f" % max(1, dmg), (255, 255, 255), 0.6)
        self.g.sfx.play("hit")

    def update(self, dt, now):
        g = self.g
        self.assign()
        if g.take("bot") and not g.mouse_mode:
            self.use_bot = not self.use_bot
            self.bot = BotCtl() if self.use_bot else None
            self.state = "WAIT"
            self.t_wait = 0.0
            self.wins = [0, 0]
            self.round = 1
            g.toast("BOT " + ("ON" if self.use_bot else "OFF"))
            self.assign()
        if self.bot is not None and (self.use_bot or g.mouse_mode):
            self.bot.update(now, dt, self.pl[0].ctl)
        ready = all(p.ctl is not None and p.ctl.present for p in self.pl)
        if g.take("cycle"):
            self.pl[0].ar.cycle(1)
        for i in range(len(ORDER) - 1):          # 숫자키로 P1 무기 선택 (수류탄 제외)
            if g.take("w%d" % (i + 1)):
                if self.pl[0].ar.select(GUNS[i]):
                    g.sfx.play("ui")
        if self.state == "WAIT":
            self.t_wait = self.t_wait + dt if ready else 0.0
            if self.t_wait > 1.0:
                self.reset_round(now)
        elif self.state == "READY":
            left = self.t_state - now
            n = int(math.ceil(left))
            if n != self.last_count and n >= 1:
                self.last_count = n
                g.sfx.play("beep")
            if left <= 0:
                self.state = "PLAY"
                g.sfx.play("go")
        elif self.state == "PLAY":
            self.play(dt, now)
        elif self.state == "ROUND":
            if now >= self.t_state:
                self.round += 1
                self.reset_round(now)
        elif self.state == "MATCH":
            c = g.ptr()
            if c.present and c.fire_edge:
                a, b = self.over_rects()
                if inside(a, c.pos):
                    g.go("pvp")
                elif inside(b, c.pos):
                    g.go("menu")

    def over_rects(self):
        cx, y, bw, bh = V.W // 2, int(V.H * 0.70), S(220), S(56)
        return (cx - bw - S(10), y, cx - S(10), y + bh), (cx + S(10), y, cx + bw + S(10), y + bh)

    def play(self, dt, now):
        g = self.g
        cover = self.cover(now)
        for i, p in enumerate(self.pl):
            foe = self.pl[1 - i]
            c = p.ctl
            p.flash = max(0.0, p.flash - dt)
            if c is None or not c.present:
                continue
            if isinstance(c, MouseCtl):
                dx, dy = foe.ctl.center[0] - c.center[0], foe.ctl.center[1] - c.center[1]
                d = math.hypot(dx, dy) or 1.0
                c.dir = (dx / d, dy / d)
                c.tip = (c.center[0] + c.dir[0] * S(50), c.center[1] + c.dir[1] * S(50))
            if p.ar.update(now):
                g.sfx.play("reload")
            if c.switch_edge:
                p.ar.cycle(1)
                g.sfx.play("ui")
            if c.reload_edge or (i == 0 and g.take("reload")):
                if p.ar.start_reload(now):
                    g.sfx.play("reload")
            want = c.trigger if p.ar.w["auto"] else c.fire_edge
            if want and not c.guard:
                self.shoot(p, foe, now)
        # 총알 이동 / 충돌
        alive = []
        for b in self.bullets:
            b[2], b[3] = b[0], b[1]
            b[0] += b[4] * dt
            b[1] += b[5] * dt
            b[8] -= dt
            if b[8] <= 0 or not (-50 < b[0] < V.W + 50 and -50 < b[1] < V.H + 50):
                continue
            blocked = False
            for k in range(1, 5):
                px, py = b[2] + (b[0] - b[2]) * k / 4, b[3] + (b[1] - b[3]) * k / 4
                if cover[0] <= px <= cover[2] and cover[1] <= py <= cover[3]:
                    g.fx.burst(px, py, (200, 200, 200), 4, 160, 0.2, 2, 0)
                    blocked = True
                    break
            if blocked:
                continue
            foe = self.pl[1 - b[6]]
            if foe.ctl is not None and foe.ctl.present and seg_circle((b[2], b[3]), (b[0], b[1]), foe.ctl.center, self.radius(foe)):
                self.damage(foe, self.pl[b[6]], b[7], b[0], b[1])
                if foe.hp <= 0:
                    self.round_end(self.pl[b[6]], now)
                    break
                continue
            alive.append(b)
        if self.state == "PLAY":
            self.bullets = alive

    def round_end(self, winner, now):
        self.wins[winner.idx] += 1
        self.winner = winner
        self.bullets = []
        self.g.sfx.play("boom")
        self.g.fx.shake = 14
        if max(self.wins) >= 2:
            self.state = "MATCH"
            self.g.sfx.play("win")
            if not self.rewarded:
                self.rewarded = True
                sv = self.g.save.d
                sv["coins"] += 30
                sv["best"]["pvp_matches"] += 1
                self.g.save.write()
        else:
            self.state = "ROUND"
            self.t_state = now + 2.5

    def draw(self, bg, now):
        g = self.g
        W, H = V.W, V.H
        img = cv2.convertScaleAbs(bg, alpha=0.62)
        cv = self.cover(now)
        cv2.rectangle(img, (int(cv[0]), int(cv[1])), (int(cv[2]), int(cv[3])), (110, 110, 120), -1)
        cv2.rectangle(img, (int(cv[0]), int(cv[1])), (int(cv[2]), int(cv[3])), (200, 200, 210), T(2))
        for p in self.pl:
            c = p.ctl
            if c is None or not c.present:
                continue
            if g.skel and c.pts:
                g.skeleton(img, c, p.col, thin=True)
            ctr, r = P2(c.center), int(self.radius(p))
            cv2.circle(img, ctr, r, C(p.col), T(2), cv2.LINE_AA)
            if p.flash > 0:
                cv2.circle(img, ctr, r, (255, 255, 255), -1 if p.flash > 0.12 else T(4), cv2.LINE_AA)
            if c.guard:
                cv2.circle(img, ctr, r + S(10), (255, 220, 120), T(4), cv2.LINE_AA)
            tip = c.tip
            end = (tip[0] + c.dir[0] * S(240), tip[1] + c.dir[1] * S(240))
            ov = img.copy()
            cv2.line(ov, P2(tip), P2(end), C(p.col), T(2), cv2.LINE_AA)
            cv2.addWeighted(ov, 0.5, img, 0.5, 0, img)
            cv2.circle(img, P2(tip), S(6), C(p.col), -1, cv2.LINE_AA)
            text(img, "P%d" % (p.idx + 1) + (" BOT" if isinstance(c, BotCtl) else ""), ctr[0], ctr[1] - r - S(8), 0.6, p.col, 2, "c")
        for b in self.bullets:
            cv2.line(img, P2(b[2:4]), P2(b[0:2]), C(PCOL[b[6]]), T(4), cv2.LINE_AA)
            cv2.circle(img, P2(b[0:2]), S(5), (255, 255, 255), -1, cv2.LINE_AA)
        g.fx.draw(img)
        # HUD
        for i, p in enumerate(self.pl):
            bw = S(330)
            x = S(16) if i == 0 else W - S(16) - bw
            bar(img, x, S(16), bw, S(24), p.hp / 100.0, p.col)
            text(img, "P%d  HP %d" % (i + 1, max(0, int(p.hp))), x + (S(8) if i == 0 else bw - S(8)), S(35), 0.6, (255, 255, 255), 2, "l" if i == 0 else "r")
            wtxt = "%s  %s" % (p.ar.w["name"], "RELOAD" if p.ar.reloading() else p.ar.ammo_text())
            text(img, wtxt, x + (0 if i == 0 else bw), S(62), 0.55, p.ar.w["col"], 1, "l" if i == 0 else "r")
            for k in range(2):
                cv2.circle(img, (x + (S(10) + k * S(22) if i == 0 else bw - S(10) - k * S(22)), S(78)), S(8),
                           C(p.col), -1 if k < self.wins[i] else T(2), cv2.LINE_AA)
        text(img, "ROUND %d" % self.round, W // 2, S(36), 0.8, (255, 255, 255), 2, "c")
        text(img, "%d : %d" % tuple(self.wins), W // 2, S(66), 0.8, (0, 220, 255), 2, "c")
        hint = "gun pose: aim  |  thumb: fire  |  palm: reload  |  peace: switch  |  fist: guard"
        text(img, hint, W // 2, H - S(14), 0.45, (210, 210, 210), 1, "c")
        if self.state == "WAIT":
            missing = [str(i + 1) for i, p in enumerate(self.pl) if p.ctl is None or not p.ctl.present]
            text(img, "PVP DUEL", W // 2, int(H * 0.22), 1.6, (0, 255, 255), 3, "c")
            text(img, "Two players stand side by side. Each shows ONE hand to the camera.", W // 2, int(H * 0.30), 0.6, (230, 230, 230), 1, "c")
            text(img, "Left hand on screen = P1   Right = P2.   Dodge bullets, shoot the other player's hand!", W // 2, int(H * 0.35), 0.55, (230, 230, 230), 1, "c")
            if missing:
                text(img, "WAITING FOR PLAYER %s ...   (press B to play vs BOT)" % " & ".join(missing), W // 2, int(H * 0.48), 0.75, (0, 200, 255), 2, "c")
            else:
                text(img, "READY!", W // 2, int(H * 0.48), 1.0, (80, 255, 80), 2, "c")
        elif self.state == "READY":
            text(img, "ROUND %d" % self.round, W // 2, int(H * 0.28), 1.6, (0, 255, 255), 3, "c")
            text(img, str(max(0, int(math.ceil(self.t_state - now)))), W // 2, int(H * 0.45), 3.0, (255, 255, 255), 4, "c")
        elif self.state == "ROUND":
            text(img, "P%d WINS THE ROUND" % (self.winner.idx + 1), W // 2, int(H * 0.4), 1.4, self.winner.col, 3, "c")
        elif self.state == "MATCH":
            shade(img, 0, 0, W, H, (0, 0, 0), 0.6)
            text(img, "P%d WINS THE MATCH!" % (self.winner.idx + 1), W // 2, int(H * 0.3), 1.8, self.winner.col, 4, "c", FONT_B)
            text(img, "%d : %d      +$30" % tuple(self.wins), W // 2, int(H * 0.45), 0.9, (255, 255, 255), 2, "c")
            c = g.ptr()
            a, b = self.over_rects()
            btn_draw(img, a, "REMATCH", c.present and inside(a, c.pos), False, (40, 100, 40), 0, 0.8)
            btn_draw(img, b, "MENU", c.present and inside(b, c.pos), False, (100, 60, 40), 0, 0.8)
            g.draw_cursor(img, c)
        return img


# ===================== 인벤토리 / 상점 =====================
class Inventory(Mode):
    name = "inv"

    def __init__(self, g):
        super().__init__(g)
        self.tab = "BAG"
        self.msg, self.msg_until = "", 0.0

    def rows(self):
        d = self.g.save.d
        R = []
        if self.tab == "BAG":
            for gn in GUNS:
                w, own = WEAPONS[gn], gn in d["owned"]
                ammo = "INF" if gn == "pistol" else str(d["ammo"].get(gn, 0))
                sub = "DMG %d%s   MAG %d   AMMO %s" % (w["dmg"], ("x%d" % w["pellets"]) if w["pellets"] > 1 else "", w["mag"], ammo)
                if own:
                    eq = d["equipped"] == gn
                    R.append(dict(key=("equip", gn), title=w["name"], sub=sub, btn="EQUIPPED" if eq else "EQUIP", en=not eq, col=w["col"]))
                else:
                    R.append(dict(key=("none", gn), title=w["name"], sub="Locked - buy it in the SHOP", btn="LOCKED", en=False, col=(110, 110, 110)))
            # 듀얼 무기 (양손 아킴보)
            R.append(dict(key=("none", None), title="--- DUAL WIELD (양손 권총) ---", sub="양손에 각각 무기를 쥐고 탕-탕!", btn="", en=False, col=(100, 100, 100)))
            for gn in DUAL_GUNS:
                w = DUAL_WEAPONS[gn]
                own = gn in d["owned"]
                if own:
                    eq = d["equipped"] == gn
                    R.append(dict(key=("equip", gn), title=w["name"], sub="양손 동시 발사", btn="EQUIPPED" if eq else "EQUIP", en=not eq, col=w["col"]))
                else:
                    R.append(dict(key=("none", gn), title=w["name"], sub="Locked - buy in SHOP", btn="LOCKED", en=False, col=(110, 110, 110)))
            for it in ("medkit", "armor", "grenade"):
                R.append(dict(key=("none", it), title=ITEMS[it]["name"], sub=ITEMS[it]["desc"], btn="x%d" % d["items"][it], en=False, col=(210, 210, 210)))
            b = d["best"]
            R.append(dict(key=("none", "stats"), title="RECORDS", sub="BEST WAVE %d  SCORE %d  RANGE %d  KILLS %d  PVP %d" % (
                b["pve_wave"], b["pve_score"], b["range"], d["kills"], b["pvp_matches"]), btn="", en=False, col=(210, 210, 210)))
        else:
            for gn in GUNS:
                w = WEAPONS[gn]
                if gn in d["owned"]:
                    R.append(dict(key=("none", gn), title=w["name"], sub="Already owned", btn="OWNED", en=False, col=w["col"]))
                else:
                    R.append(dict(key=("buyw", gn), title=w["name"], sub="DMG %d%s  MAG %d" % (w["dmg"], ("x%d" % w["pellets"]) if w["pellets"] > 1 else "", w["mag"]),
                                  btn="BUY $%d" % w["price"], en=d["coins"] >= w["price"], col=w["col"]))
            # 듀얼 무기 샵
            R.append(dict(key=("none", None), title="--- DUAL WIELD ---", sub="양손에 각각 같은 무기를 들고 발사", btn="", en=False, col=(100, 100, 100)))
            for gn in DUAL_GUNS:
                w = DUAL_WEAPONS[gn]
                if gn in d["owned"]:
                    R.append(dict(key=("none", gn), title=w["name"], sub="Already owned", btn="OWNED", en=False, col=w["col"]))
                else:
                    R.append(dict(key=("buyw", gn), title=w["name"], sub="DUAL %s" % w["name"],
                                  btn="BUY $%d" % w["price"], en=d["coins"] >= w["price"], col=w["col"]))
            for gn in DUAL_GUNS:
                w = DUAL_WEAPONS[gn]
                own = gn in d["owned"]
                R.append(dict(key=("buya", gn), title="%s AMMO +%d" % (w["name"], w["pack"]),
                              sub=("Have: %d" % d["ammo"].get(gn, 0)) if own else "Buy the weapon first",
                              btn="$%d" % w["packcost"] if own else "LOCKED", en=own and d["coins"] >= w["packcost"], col=w["col"]))
            for gn in GUNS[1:]:
                w, own = WEAPONS[gn], gn in d["owned"]
                R.append(dict(key=("buya", gn), title="%s AMMO +%d" % (w["name"], w["pack"]),
                              sub=("Have: %d" % d["ammo"].get(gn, 0)) if own else "Buy the weapon first",
                              btn="$%d" % w["packcost"] if own else "LOCKED", en=own and d["coins"] >= w["packcost"], col=w["col"]))
            for it in ("medkit", "armor", "grenade"):
                R.append(dict(key=("buyi", it), title=ITEMS[it]["name"], sub=ITEMS[it]["desc"] + "   (have %d)" % d["items"][it],
                              btn="$%d" % ITEMS[it]["price"], en=d["coins"] >= ITEMS[it]["price"], col=(210, 210, 210)))
        return R

    def layout(self):
        W, H = V.W, V.H
        rows = self.rows()
        top, bot = S(110), H - S(80)
        cols = 2 if W >= 1.2 * H else 1
        per = int(math.ceil(len(rows) / cols))
        gap = S(8)
        rh = int(clamp((bot - top) / per - gap, S(40), S(66)))
        cw = (W - S(30) * (cols + 1)) // cols
        out = []
        for i, r in enumerate(rows):
            c, k = i // per, i % per
            x0 = S(30) + c * (cw + S(30))
            y0 = top + k * (rh + gap)
            r["rect"] = (x0, y0, x0 + cw, y0 + rh)
            r["btnr"] = (x0 + cw - S(150), y0 + S(8), x0 + cw - S(8), y0 + rh - S(8))
            out.append(r)
        tabs = {"BAG": (S(30), S(20), S(30) + S(150), S(20) + S(52)), "SHOP": (S(190), S(20), S(190) + S(150), S(20) + S(52))}
        back = (W // 2 - S(110), H - S(66), W // 2 + S(110), H - S(14))
        return out, tabs, back

    def act(self, key):
        d, sv = self.g.save.d, self.g.save
        kind, name = key
        if kind == "equip":
            d["equipped"] = name
            # 듀얼 무장 모드 토글
            if name in DUAL_WEAPONS:
                self.g.ar.set_dual(True)
                self.say("EQUIPPED %s (DUAL)" % DUAL_WEAPONS[name]["name"])
            else:
                self.g.ar.set_dual(False)
                self.say("EQUIPPED " + WEAPONS[name]["name"])
        elif kind == "buyw":
            w = WEAPONS.get(name) or DUAL_WEAPONS.get(name)
            d["coins"] -= w["price"]
            d["owned"].append(name)
            d["equipped"] = name
            base = w.get("base", name)
            d["ammo"][base] = d["ammo"].get(base, 0) + w["pack"]
            if name in DUAL_WEAPONS:
                self.g.ar.set_dual(True)
                self.say("BOUGHT %s (DUAL)" % w["name"])
            else:
                self.say("BOUGHT " + w["name"])
        elif kind == "buya":
            w = WEAPONS.get(name) or DUAL_WEAPONS.get(name)
            d["coins"] -= w["packcost"]
            base = w.get("base", name)
            d["ammo"][base] = d["ammo"].get(base, 0) + w["pack"]
            self.say("AMMO +%d" % w["pack"])
        elif kind == "buyi":
            d["coins"] -= ITEMS[name]["price"]
            d["items"][name] += 1
            self.say("BOUGHT " + ITEMS[name]["name"])
        sv.write()
        self.g.sfx.play("coin")

    def say(self, s):
        self.msg, self.msg_until = s, self.g.now + 1.6

    def update(self, dt, now):
        ctl = self.g.ptr()
        if not (ctl.present and ctl.fire_edge):
            return
        rows, tabs, back = self.layout()
        for t, r in tabs.items():
            if inside(r, ctl.pos):
                self.tab = t
                self.g.sfx.play("ui")
                return
        if inside(back, ctl.pos):
            self.g.go("menu")
            return
        for r in rows:
            if inside(r["btnr"], ctl.pos):
                if r["en"]:
                    self.act(r["key"])
                else:
                    self.say("NOT AVAILABLE" if r["btn"] not in ("EQUIPPED", "OWNED") else "ALREADY DONE")
                    self.g.sfx.play("empty")
                return

    def draw(self, bg, now):
        g = self.g
        ctl = g.ptr()
        img = cv2.convertScaleAbs(bg, alpha=0.35)
        rows, tabs, back = self.layout()
        for t, r in tabs.items():
            btn_draw(img, r, t, ctl.present and inside(r, ctl.pos), self.tab == t, (80, 60, 30), 0, 0.75)
        text(img, "$ %d" % g.save.d["coins"], V.W - S(30), S(56), 1.1, (0, 215, 255), 2, "r")
        for r in rows:
            x0, y0, x1, y1 = r["rect"]
            shade(img, x0, y0, x1, y1, (30, 30, 30), 0.7)
            cv2.rectangle(img, (x0, y0), (x1, y1), (110, 110, 110), 1)
            cv2.rectangle(img, (x0, y0), (x0 + S(6), y1), C(r["col"]), -1)
            text(img, r["title"], x0 + S(16), y0 + int((y1 - y0) * 0.42), 0.7, (255, 255, 255), 2)
            text(img, r["sub"], x0 + S(16), y0 + int((y1 - y0) * 0.78), 0.45, (200, 200, 200), 1)
            if r["btn"]:
                btn_draw(img, r["btnr"], r["btn"], ctl.present and inside(r["btnr"], ctl.pos), False, (50, 90, 50), 0, 0.55, r["en"])
        btn_draw(img, back, "BACK", ctl.present and inside(back, ctl.pos), False, (100, 60, 40), 0, 0.75)
        if now < self.msg_until:
            text(img, self.msg, V.W // 2, V.H - S(84), 0.8, (0, 255, 255), 2, "c")
        g.draw_hand(img, g.hand_main if not g.mouse_mode else None)
        g.draw_cursor(img, ctl)
        return img


# ===================== 튜토리얼 =====================
TUT = {
    "aim": dict(title="AIM", pose="GUN",
                cam="Make a GUN POSE: index finger pointing out, the other fingers curled. Your fingertip is the "
                    "crosshair - keep it inside the ring for one second.",
                mouse="Move the mouse and keep the crosshair inside the ring for one second."),
    "fire": dict(title="FIRE", pose="GUN",
                 cam="Keep the gun pose and FOLD YOUR THUMB DOWN like pulling a trigger. Open the thumb again before "
                     "the next shot. Hit 3 targets.",
                 mouse="Left-click (or press SPACE) to shoot. Hit 3 targets."),
    "reload": dict(title="RELOAD", pose="PALM",
                   cam="Open your whole hand (OPEN PALM) and hold it for a moment until the ring fills.",
                   mouse="Right-click (or press R) to reload."),
    "switch": dict(title="SWITCH WEAPON", pose="PEACE",
                   cam="Show a PEACE sign (index + middle finger up). Switch weapons twice.",
                   mouse="Middle-click (or press TAB) to switch weapons. Do it twice."),
    "guard": dict(title="GUARD", pose="FIST",
                  cam="Make a FIST and hold it for one second. Guarding cuts the damage you take.",
                  mouse="Press G to toggle guard and keep it on for one second."),
    "dwell": dict(title="HUD BUTTONS", pose="GUN",
                  cam="In-game buttons (MENU, MEDKIT, ARMOR, weapon slots) activate when you point at them for about "
                      "one second. Try it on the button.",
                  mouse="In-game buttons activate when the crosshair rests on them for about one second. Try it."),
    "calib": dict(title="CALIBRATE TRIGGER", pose="GUN", cam="", mouse=""),
    "done": dict(title="ALL SET", pose="", cam="", mouse=""),
}


class Tutorial(Mode):
    """단계별 제스처 연습 + 방아쇠(엄지) 보정. 마우스 모드에서도 동작"""
    name = "tutorial"

    def __init__(self, g):
        super().__init__(g)
        self.sid = "aim"
        self.target = None
        self.saved_done = False
        self.init_step()

    # ---------- 단계 관리 ----------
    def order(self):
        o = ["aim", "fire", "reload", "switch", "guard", "dwell"]
        if not self.g.mouse_mode:
            o.append("calib")
        o.append("done")
        return o

    def init_step(self):
        self.t = 0.0
        self.hits = 0
        self.sw = 0
        self.passed = False
        self.pass_until = 0.0
        self.cal_phase = 0
        self.cal_t = 0.0
        self.cal_samples = []
        self.cal_open = 0.0
        self.cal_msg = ""
        self.dwell = Dwell()
        self.new_target()
        if self.sid == "aim":
            self.target = (V.W / 2.0, V.H * 0.52, S(70))

    def new_target(self):
        W, H = V.W, V.H
        old = self.target
        x, y = W / 2.0, H * 0.52
        for _ in range(20):
            x, y = random.uniform(0.2, 0.8) * W, random.uniform(0.40, 0.66) * H
            if old is None or math.hypot(x - old[0], y - old[1]) > S(160):
                break
        self.target = (x, y, S(62))

    def advance(self):
        o = self.order()
        i = o.index(self.sid) if self.sid in o else len(o) - 2
        self.sid = o[min(i + 1, len(o) - 1)]
        self.init_step()
        if self.sid == "done" and not self.saved_done:
            self.saved_done = True
            self.g.save.d["settings"]["tutorial_done"] = True
            self.g.save.write()

    def complete(self, now):
        self.passed = True
        self.pass_until = now + 0.8
        self.g.sfx.play("win")
        self.g.fx.text(V.W // 2, int(V.H * 0.30), "NICE!", (80, 255, 80), 1.4)

    def btn_rects(self):
        W, H = V.W, V.H
        y0, y1 = H - S(66), H - S(14)
        if self.sid == "done":
            return {"replay": (W // 2 - S(230), y0, W // 2 - S(10), y1),
                    "finish": (W // 2 + S(10), y0, W // 2 + S(230), y1)}
        return {"back": (S(20), y0, S(200), y1), "skip": (W - S(200), y0, W - S(20), y1)}

    def dwell_rect(self):
        W, H = V.W, V.H
        return (W // 2 - S(130), int(H * 0.5) - S(34), W // 2 + S(130), int(H * 0.5) + S(34))

    # ---------- 업데이트 ----------
    def update(self, dt, now):
        g = self.g
        ctl = g.ptr()
        if g.mouse_mode and self.sid == "calib":
            self.advance()
        if ctl.present and ctl.fire_edge:
            for k, r in self.btn_rects().items():
                if inside(r, ctl.pos):
                    g.sfx.play("ui")
                    if k in ("back", "finish"):
                        g.go("menu")
                    elif k == "skip":
                        self.advance()
                    elif k == "replay":
                        self.sid = "aim"
                        self.init_step()
                    return
        if g.take("next"):
            if self.sid == "done":
                g.go("menu")
            else:
                self.advance()
            return
        if self.passed:
            if now >= self.pass_until:
                self.advance()
            return
        sid = self.sid
        if sid == "aim":
            cx, cy, r = self.target
            inn = ctl.present and math.hypot(ctl.pos[0] - cx, ctl.pos[1] - cy) <= r
            self.t = self.t + dt if inn else max(0.0, self.t - dt * 2)
            if self.t >= 1.0:
                self.complete(now)
        elif sid == "fire":
            if ctl.present and ctl.fire_edge:
                pos = ctl.shot_pos()
                cx, cy, r = self.target
                g.sfx.play("shot")
                if math.hypot(pos[0] - cx, pos[1] - cy) <= r:
                    self.hits += 1
                    g.fx.burst(cx, cy, (60, 60, 255), 14, 260, 0.4, 3)
                    g.fx.text(cx, cy - r, "HIT!", (0, 215, 255), 0.9)
                    g.sfx.play("hit")
                    if self.hits >= 3:
                        self.complete(now)
                    else:
                        self.new_target()
                else:
                    g.fx.burst(pos[0], pos[1], (200, 200, 200), 4, 140, 0.25, 2, 0)
                    g.fx.text(pos[0], pos[1] - S(16), "MISS", (180, 180, 180), 0.6)
        elif sid == "reload":
            if ctl.reload_edge or g.take("reload"):
                g.sfx.play("reload")
                self.complete(now)
        elif sid == "switch":
            if ctl.switch_edge or g.take("cycle"):
                self.sw += 1
                g.sfx.play("ui")
                if self.sw >= 2:
                    self.complete(now)
        elif sid == "guard":
            self.t = self.t + dt if (ctl.present and ctl.guard) else max(0.0, self.t - dt * 2)
            if self.t >= 1.0:
                self.complete(now)
        elif sid == "dwell":
            hov = "tgt" if (ctl.present and inside(self.dwell_rect(), ctl.pos)) else None
            if self.dwell.update(hov, dt):
                self.complete(now)
        elif sid == "calib":
            self.update_calib(ctl, dt, now)

    def update_calib(self, ctl, dt, now):
        """엄지 활짝 -> 엄지 접기 두 구간을 측정해 사용자별 방아쇠 기준값을 계산/저장"""
        good = ctl.present and getattr(ctl, "raw", "") == "GUN"
        if self.cal_phase == 0:
            if good:
                self.cal_samples.append(ctl.tr)
                self.cal_t += dt
            else:
                self.cal_t = max(0.0, self.cal_t - dt)
            if self.cal_t >= 1.5 and len(self.cal_samples) >= 8:
                self.cal_open = float(np.median(self.cal_samples))
                self.cal_phase, self.cal_t, self.cal_samples = 1, 0.0, []
                self.g.sfx.play("coin")
            return
        folded = good and ctl.tr < self.cal_open - 0.05
        if folded:
            self.cal_samples.append(ctl.tr)
            self.cal_t += dt
        else:
            self.cal_t = max(0.0, self.cal_t - dt * 2)
        if self.cal_t >= 1.2 and len(self.cal_samples) >= 8:
            closed = float(np.median(self.cal_samples))
            span = self.cal_open - closed
            if span < 0.12:
                self.cal_msg = "Thumb movement was too small - let's try again."
                self.cal_phase, self.cal_t, self.cal_samples = 0, 0.0, []
                self.g.sfx.play("empty")
                return
            down = clamp(closed + 0.38 * span, 0.10, 1.0)
            up = max(closed + 0.62 * span, down + 0.06)
            GESTURE.update(trig_down=down, trig_up=up)
            sv = self.g.save
            sv.d["settings"]["trig"] = [round(down, 3), round(up, 3)]
            sv.write()
            self.cal_msg = "SAVED:  fire < %.2f    release > %.2f" % (down, up)
            self.complete(now)

    def calib_text(self):
        if self.passed:
            return self.cal_msg
        pre = (self.cal_msg + "   ") if self.cal_msg else ""
        if self.cal_phase == 0:
            return pre + "Step 1/2 - make a GUN POSE and keep your THUMB OPEN, away from the index finger. Hold still."
        return "Step 2/2 - now FOLD your thumb down, as if pulling the trigger, and hold it."

    # ---------- 그리기 ----------
    def meter(self, img, ctl):
        W, H = V.W, V.H
        x0, y0, w, h = W // 2 - S(160), H - S(116), S(320), S(14)
        mx = 1.2
        bar(img, x0, y0, w, h, (ctl.tr / mx) if ctl.present else 0.0, (0, 200, 255))
        for key, col, lab, up in (("trig_down", (0, 255, 0), "FIRE", True), ("trig_up", (80, 80, 255), "RELEASE", False)):
            x = x0 + int(w * clamp(GESTURE[key] / mx, 0, 1))
            cv2.line(img, (x, y0 - S(6)), (x, y0 + h + S(6)), col, T(2))
            text(img, lab, x, (y0 - S(10)) if up else (y0 + h + S(22)), 0.4, col, 1, "c")
        text(img, "THUMB %.2f" % ctl.tr, x0 + w + S(12), y0 + h, 0.45, (220, 220, 220), 1)

    def chips(self, img, ctl, info):
        x, y = S(24), S(214)
        det = ctl.pose if ctl.present else "-"
        text(img, "TARGET POSE: %s" % info["pose"], x, y, 0.55, (230, 230, 230), 1)
        text(img, "DETECTED: %s" % det, x, y + S(26), 0.55, (80, 255, 80) if det == info["pose"] else (0, 200, 255), 2)
        text(img, "FINGERS", x, y + S(60), 0.5, (220, 220, 220), 1)
        for k, nm in enumerate("IMRP"):
            cx = x + S(100) + k * S(34)
            on = ctl.present and ctl.ext[k]
            cv2.circle(img, (cx, y + S(55)), S(11), (80, 220, 80) if on else (70, 70, 70), -1, cv2.LINE_AA)
            text(img, nm, cx, y + S(84), 0.45, (220, 220, 220), 1, "c")

    def draw_step(self, img, ctl, now):
        g, sid = self.g, self.sid
        W, H = V.W, V.H
        if sid in ("aim", "fire"):
            cx, cy, r = self.target
            c = (int(cx), int(cy))
            if sid == "fire":
                for rr, col in ((1.0, (240, 240, 240)), (0.65, (50, 50, 220)), (0.3, (240, 240, 240)), (0.12, (50, 50, 220))):
                    cv2.circle(img, c, max(1, int(r * rr)), col, -1, cv2.LINE_AA)
                text(img, "HITS %d / 3" % self.hits, W // 2, int(H * 0.76), 0.9, (255, 255, 255), 2, "c")
            else:
                cv2.circle(img, c, int(r), (0, 255, 255), T(3), cv2.LINE_AA)
                cv2.circle(img, c, max(2, S(4)), (0, 255, 255), -1, cv2.LINE_AA)
                if self.t > 0:
                    rr = int(r) + S(10)
                    cv2.ellipse(img, c, (rr, rr), 0, -90, -90 + int(360 * clamp(self.t, 0, 1)), (0, 255, 0), T(4), cv2.LINE_AA)
        elif sid == "reload":
            text(img, "AMMO  0 / 12", W // 2, int(H * 0.50), 1.4, (60, 60, 255), 3, "c")
            text(img, "EMPTY - RELOAD!", W // 2, int(H * 0.58), 0.9, (0, 200, 255), 2, "c")
            if ctl.present and ctl.palm_prog > 0:
                rr = S(34)
                cv2.ellipse(img, P2(ctl.pos), (rr, rr), 0, -90, -90 + int(360 * ctl.palm_prog), (0, 255, 0), T(4), cv2.LINE_AA)
        elif sid == "switch":
            wn = GUNS[self.sw % len(GUNS)]
            text(img, WEAPONS[wn]["name"], W // 2, int(H * 0.52), 1.8, WEAPONS[wn]["col"], 3, "c")
            text(img, "SWITCHED %d / 2" % self.sw, W // 2, int(H * 0.62), 0.9, (255, 255, 255), 2, "c")
        elif sid == "guard":
            c, rr = (W // 2, int(H * 0.52)), S(90)
            on = ctl.present and ctl.guard
            cv2.circle(img, c, rr, (255, 220, 120) if on else (110, 110, 110), T(5), cv2.LINE_AA)
            if self.t > 0:
                cv2.ellipse(img, c, (rr + S(14), rr + S(14)), 0, -90, -90 + int(360 * clamp(self.t, 0, 1)), (0, 255, 0), T(4), cv2.LINE_AA)
            text(img, "GUARD" if on else "...", c[0], c[1] + S(10), 1.0, (255, 255, 255), 2, "c")
        elif sid == "dwell":
            r = self.dwell_rect()
            btn_draw(img, r, "POINT HERE", ctl.present and inside(r, ctl.pos), False, (70, 70, 40),
                     self.dwell.prog("tgt"), 0.9)
        elif sid == "calib":
            need = 1.5 if self.cal_phase == 0 else 1.2
            if not self.passed:
                bar(img, W // 2 - S(150), int(H * 0.5), S(300), S(16), self.cal_t / need, (0, 255, 0))
                text(img, "HOLD" if self.cal_t > 0 else "WAITING FOR POSE...", W // 2, int(H * 0.5) + S(46), 0.7, (255, 255, 255), 2, "c")
            else:
                text(img, "TRIGGER CALIBRATED", W // 2, int(H * 0.5), 1.2, (80, 255, 80), 2, "c")
        elif sid == "done":
            if g.mouse_mode:
                lines = ["Mouse: move = aim    left-click = fire    right-click = reload",
                         "middle-click = switch weapon    G = guard    SPACE / R / TAB also work"]
            else:
                lines = ["GUN POSE = aim      THUMB DOWN = fire",
                         "OPEN PALM = reload      PEACE SIGN = switch weapon      FIST = guard",
                         "Point at HUD buttons for 1 second to use them",
                         "Trigger:  fire < %.2f    release > %.2f   (press I in game for gesture debug)" % (
                             GESTURE["trig_down"], GESTURE["trig_up"]),
                         "Tips: good front lighting, keep your whole hand in view, and recalibrate if firing feels off"]
            text(img, "YOU'RE READY!", W // 2, int(H * 0.30), 1.6, (80, 255, 80), 3, "c")
            for i, ln in enumerate(lines):
                text(img, ln, W // 2, int(H * 0.42) + i * S(34), 0.65, (255, 255, 255), 1, "c")

    def draw(self, bg, now):
        g = self.g
        ctl = g.ptr()
        W, H = V.W, V.H
        sid = self.sid
        info = TUT[sid]
        o = self.order()
        idx = o.index(sid) + 1 if sid in o else len(o)
        img = cv2.convertScaleAbs(bg, alpha=0.5)

        text(img, "TUTORIAL  %d/%d   %s" % (idx, len(o), info["title"]), W // 2, S(44), 1.0, (0, 220, 255), 2, "c")
        bar(img, W // 2 - S(200), S(56), S(400), S(8), idx / float(len(o)), (0, 255, 255))
        msg = info["mouse"] if g.mouse_mode else info["cam"]
        if sid == "calib":
            msg = self.calib_text()
        lines = textwrap.wrap(msg, max(24, int(W * 0.86 / (11.5 * V.s)))) if msg else []
        if lines:
            shade(img, W * 0.05, S(76), W * 0.95, S(76) + len(lines) * S(26) + S(12), (0, 0, 0), 0.55)
            for i, ln in enumerate(lines):
                text(img, ln, W // 2, S(100) + i * S(26), 0.62, (255, 255, 255), 1, "c")

        self.draw_step(img, ctl, now)
        g.fx.draw(img)
        g.draw_hand(img, g.hand_main if not g.mouse_mode else None)
        if not g.mouse_mode and info["pose"]:
            self.chips(img, ctl, info)
        if not g.mouse_mode and sid in ("fire", "calib"):
            self.meter(img, ctl)
        if not ctl.present and int(now * 2) % 2 == 0:
            text(img, "SHOW YOUR HAND  (or press V for mouse)", W // 2, int(H * 0.84), 0.8, (0, 255, 255), 2, "c")
        labels = {"back": "BACK", "skip": "SKIP STEP", "finish": "FINISH", "replay": "REPLAY"}
        for k, r in self.btn_rects().items():
            btn_draw(img, r, labels[k], ctl.present and inside(r, ctl.pos), False,
                     (40, 100, 40) if k == "finish" else (80, 60, 30), 0, 0.7)
        g.draw_cursor(img, ctl)
        return img


# ===================== 게임 본체 =====================
class Game:
    def __init__(self, mouse_mode=False):
        self.save = Save()
        self.sfx = Sfx(bool(self.save.d["settings"].get("sound", True)))
        tg = self.save.d["settings"].get("trig")          # 튜토리얼에서 보정한 방아쇠 기준값
        if isinstance(tg, (list, tuple)) and len(tg) == 2 and 0.05 < tg[0] < tg[1] < 1.5:
            GESTURE.update(trig_down=float(tg[0]), trig_up=float(tg[1]))
        self.main_prev = None
        self.fx = FX()
        self.mouse = MouseCtl()
        self.hand_main = HandCtl()
        self.hand_lr = [HandCtl(), HandCtl()]
        self.mouse_mode = mouse_mode
        self.keys = set()
        self.quit = False
        self.paused = False
        self.debug = False
        self.skel = True
        self.fullscreen_req = False
        self.cache = {}
        self.now = 0.0
        self.toasts = []
        self.fps = 0.0
        self.cam_index = 1   # 기본 카메라 번호 (고정값: 1)
        self.cap = None      # 카메라 캡처 객체
        self.mode = Menu(self)
        self.volume = float(self.save.d["settings"].get("volume", 1.0))   # 사운드 볼륨 0.0~1.0
        self.debug_tune = False   # 디버그 모드에서 실시간 튜닝 활성화
        self.auto_save_t = 0.0    # 자동 저장 타이머

    # ---------- 유틸 ----------
    def ptr(self):
        return self.mouse if self.mouse_mode else self.hand_main

    def take(self, k):
        if k in self.keys:
            self.keys.discard(k)
            return True
        return False

    def toast(self, s, sec=1.6):
        self.toasts.append([s, self.now + sec])

    def go(self, name):
        self.mode.leave()
        self.fx = FX()
        self.paused = False
        if name == "quit":
            self.quit = True
            return
        self.mode = {"menu": Menu, "pve": PvE, "pvp": PvP, "range": Range, "inv": Inventory,
                     "tutorial": Tutorial}[name](self)
        # 듀얼 무장 상태 동기화
        if name in ("pve", "pvp", "range") and hasattr(self, 'ar'):
            equipped = self.save.d.get("equipped", "pistol")
            if equipped in DUAL_WEAPONS:
                self.ar.set_dual(True)
            else:
                self.ar.set_dual(False)

    def resize(self, W, H):
        W, H = int(W) // 2 * 2, int(H) // 2 * 2
        if (W, H) == (V.W, V.H):
            return
        V.set(W, H)
        self.cache.clear()

    # ---------- 입력 ----------
    def on_mouse(self, ev, x, y, flags, param=None):
        self.mouse.event(ev, x, y, flags)

    def on_key(self, k):
        global PUNCH_DOWN
        if k == 255 or k < 0:
            return
        ch = chr(k).lower() if 0 <= k < 128 else ""
        if k == 27:
            if isinstance(self.mode, Menu):
                self.quit = True
            else:
                self.go("menu")
        elif ch == " ":
            self.keys.add("fire")
        elif ch == "r":
            self.keys.add("reload")
        elif ch == "\t":
            self.keys.add("cycle")
        elif ch and ch in "123456":
            self.keys.add("w" + ch)
        elif ch == "h":
            self.keys.add("medkit")
        elif ch == "a":
            self.keys.add("armor")
        elif ch == "b":
            self.keys.add("bot")
        elif ch == "n":
            self.keys.add("next")
        elif ch == "g":
            if self.mouse_mode:                      # 마우스 모드 방어: G 로 켜고 끄기
                self.mouse.guard = not self.mouse.guard
                self.toast("GUARD " + ("ON" if self.mouse.guard else "OFF"))
        elif ch == "p":
            if not isinstance(self.mode, (Menu, Inventory, Tutorial)):
                self.paused = not self.paused
        elif ch == "m":
            self.sfx.on = not self.sfx.on
            self.save.d["settings"]["sound"] = self.sfx.on
            self.save.write()
            self.toast("SOUND " + ("ON" if self.sfx.on else "OFF"))
        elif ch == "f":
            self.fullscreen_req = True
        elif ch == "k":
            self.skel = not self.skel
        elif ch == "i":
            self.debug = not self.debug
            self.debug_tune = self.debug
            self.toast("DEBUG " + ("ON" if self.debug else "OFF") + "  [Q/W TRIG_DOWN, E/R TRIG_UP, A/S PUNCH, Z/X VOLUME]")
        elif ch == "q":   # TRIG_DOWN 낮춤 (더 민감)
            if self.debug_tune:
                GESTURE["trig_down"] = max(0.05, GESTURE["trig_down"] - 0.05)
                self.toast("TRIG_DOWN: %.2f" % GESTURE["trig_down"])
        elif ch == "w":   # TRIG_DOWN 높임
            if self.debug_tune:
                GESTURE["trig_down"] = min(1.5, GESTURE["trig_down"] + 0.05)
                self.toast("TRIG_DOWN: %.2f" % GESTURE["trig_down"])
        elif ch == "e":   # TRIG_UP 낮춤
            if self.debug_tune:
                GESTURE["trig_up"] = max(0.10, GESTURE["trig_up"] - 0.05)
                self.toast("TRIG_UP: %.2f" % GESTURE["trig_up"])
        elif ch == "r":   # TRIG_UP 높임
            if self.debug_tune:
                GESTURE["trig_up"] = min(2.0, GESTURE["trig_up"] + 0.05)
                self.toast("TRIG_UP: %.2f" % GESTURE["trig_up"])
        elif ch == "a":   # PUNCH_DOWN 낮춤 (더 민감)
            if self.debug_tune:
                PUNCH_DOWN = max(0.10, PUNCH_DOWN - 0.05)
                self.toast("PUNCH_DOWN: %.2f" % PUNCH_DOWN)
        elif ch == "s":   # PUNCH_DOWN 높임
            if self.debug_tune:
                PUNCH_DOWN = min(1.0, PUNCH_DOWN + 0.05)
                self.toast("PUNCH_DOWN: %.2f" % PUNCH_DOWN)
        elif ch == "z":   # 볼륨 낮춤
            self.volume = max(0.0, self.volume - 0.1)
            self.save.d["settings"]["volume"] = self.volume
            self.save.write()
            self.toast("VOLUME: %.0f%%" % (self.volume * 100))
        elif ch == "x":   # 볼륨 높임
            self.volume = min(1.0, self.volume + 0.1)
            self.save.d["settings"]["volume"] = self.volume
            self.save.write()
            self.toast("VOLUME: %.0f%%" % (self.volume * 100))
        elif ch == "v":
            if not self.mouse_mode:
                # 카메라 모드에서 마우스 모드로 전환
                self.mouse_mode = True
                self.mouse.guard = False
                self.toast("MOUSE MODE")
            else:
                # 마우스 모드에서 카메라 모드로 전환 (기본 카메라 번호 사용)
                if self.cap is None:
                    self.cap = open_camera(self.cam_index)
                self.mouse_mode = False
                self.mouse.guard = False
                self.toast("CAMERA MODE")

    # ---------- 업데이트 ----------
    def feed_hands(self, hands, now, dt):
        W, H = V.W, V.H
        info = []
        for lm in hands:
            info.append((lm[0].x * W, math.hypot((lm[0].x - lm[9].x) * W, (lm[0].y - lm[9].y) * H), lm, lm[0].y * H))
        main = None
        if info:
            # 메인 손: 가장 큰 손. 단, 이전 프레임의 손과 가까운 손이 (크기가 비슷하면) 우선 -> 손이 바뀌며 튀는 것 방지
            big = max(info, key=lambda a: a[1])
            pick = big
            if self.main_prev is not None and len(info) > 1:
                near = min(info, key=lambda a: math.hypot(a[0] - self.main_prev[0], a[3] - self.main_prev[1]))
                if near[1] * 1.6 >= big[1]:
                    pick = near
            self.main_prev = (pick[0], pick[3])
            main = pick[2]
        else:
            self.main_prev = None
        # 시선 고정용 타겟 리스트 설정 (PvE/PvP 모드의 좀비)
        self.hand_main.ar_targets = getattr(self.mode, 'zs', None)
        self.hand_main.update(main, now, dt)
        left = right = None
        if len(info) >= 2:
            s = sorted(info, key=lambda a: a[0])
            left, right = s[0][2], s[-1][2]
        elif len(info) == 1:
            if info[0][0] < W / 2:
                left = info[0][2]
            else:
                right = info[0][2]
        self.hand_lr[0].update(left, now, dt)
        self.hand_lr[1].update(right, now, dt)
        self.mouse.update(None, now, dt)

    def keyboard_fire(self):
        """SPACE 발사: PVP에서는 P1(왼쪽 플레이어) 컨트롤러에, 그 외에는 현재 포인터에 적용"""
        tgt = self.ptr()
        if isinstance(self.mode, PvP):
            self.mode.assign()
            if self.mode.pl[0].ctl is not None:
                tgt = self.mode.pl[0].ctl
        if tgt.present:
            tgt.fire_edge = tgt.trigger = True
            tgt.lock = tgt.pos

    def update(self, hands, dt, now):
        self.now = now
        self.feed_hands(hands or [], now, dt)
        if "fire" in self.keys:
            self.keys.discard("fire")
            self.keyboard_fire()
        if not self.paused:
            self.fx.update(dt)
            self.mode.update(dt, now)
        self.keys.clear()
        self.toasts = [t for t in self.toasts if t[1] > now]
        if dt > 0:
            self.fps = self.fps * 0.9 + (1.0 / dt) * 0.1
        # 자동 저장 (5초 주기)
        self.auto_save_t += dt
        if self.auto_save_t >= 5.0:
            self.auto_save_t = 0.0
            self.save.write()

    # ---------- 그리기 ----------
    def synth_bg(self):
        key = ("sbg", V.W, V.H)
        b = self.cache.get(key)
        if b is None:
            H, W = V.H, V.W
            g = np.linspace(0, 1, H, dtype=np.float32)[:, None]
            b = np.empty((H, W, 3), np.uint8)
            b[:, :, 0] = (60 - 30 * g) * np.ones((1, W))
            b[:, :, 1] = (45 - 25 * g) * np.ones((1, W))
            b[:, :, 2] = (35 - 20 * g) * np.ones((1, W))
            for x in range(0, W, max(20, S(60))):
                cv2.line(b, (x, 0), (x, H), (70, 60, 50), 1)
            for y in range(0, H, max(20, S(60))):
                cv2.line(b, (0, y), (W, y), (70, 60, 50), 1)
            self.cache[key] = b
        return b

    def ground_mul(self):
        key = ("gm", V.W, V.H)
        m = self.cache.get(key)
        if m is None:
            H, W = V.H, V.W
            hor = int(H * 0.40)
            rows = np.where(np.arange(H) < hor, 0.80, np.linspace(0.66, 0.40, H))
            m = np.empty((H, W, 3), np.uint8)
            m[:] = (rows * 255).astype(np.uint8)[:, None, None]
            for i in range(-6, 7):
                cv2.line(m, (W // 2, hor), (W // 2 + i * W // 4, H), (225, 225, 225), 1)
            for k in range(1, 7):
                y = int(hor + (H - hor) * (k / 6.0) ** 2)
                cv2.line(m, (0, y), (W, y), (215, 215, 215), 1)
            cv2.line(m, (0, hor), (W, hor), (240, 240, 240), T(2))
            self.cache[key] = m
        return m

    def vignette(self, img, strength):
        key = ("vig", V.W, V.H)
        m = self.cache.get(key)
        if m is None:
            yy, xx = np.mgrid[0:V.H, 0:V.W]
            d = np.sqrt(((xx - V.W / 2) / (V.W / 2)) ** 2 + ((yy - V.H / 2) / (V.H / 2)) ** 2)
            m = np.clip((d - 0.45) / 0.9, 0, 1).astype(np.float32)
            self.cache[key] = m
        add = (m * 255 * clamp(strength, 0, 1)).astype(np.uint8)
        img[:, :, 2] = cv2.add(img[:, :, 2], add)

    def skeleton(self, img, ctl, col, thin=False):
        if not ctl.pts:
            return
        th = 1 if thin else T(2)
        for a, b in CONN:
            cv2.line(img, ctl.pts[a], ctl.pts[b], C(col), th, cv2.LINE_AA)
        for p in ctl.pts:
            cv2.circle(img, p, T(2) if thin else T(3), (255, 120, 0), -1)

    def draw_hand(self, img, ctl, only_small=False):
        if ctl is not None and self.skel and ctl.present:
            # 반동으로 손 전체가 뒤로 튕기는 모션
            rx, ry = ctl.recoil_dir
            r = ctl.recoil * S(14)
            pts = [(int(p[0] + rx * r), int(p[1] + ry * r)) for p in ctl.pts]
            th = T(1)
            for a, b in CONN:
                cv2.line(img, pts[a], pts[b], C((60, 220, 60)), th, cv2.LINE_AA)
            for p in pts:
                cv2.circle(img, p, T(2), (255, 120, 0), -1)

    def draw_cursor(self, img, ctl):
        if ctl.present:
            crosshair(img, ctl.pos, S(16), (255, 255, 255), T(2))

    def draw(self, cam_bg, now):
        if cam_bg is None or cam_bg.shape[:2] != (V.H, V.W):
            cam_bg = self.synth_bg()
        img = self.mode.draw(cam_bg, now)
        fx = self.fx
        if fx.hurt > 0:
            self.vignette(img, fx.hurt)
        if fx.flash > 0:
            img[:] = cv2.addWeighted(img, 1 - fx.flash, np.full_like(img, 255), fx.flash, 0)
        if fx.shake > 1:
            sh = fx.shake * V.s * 0.5
            M = np.float32([[1, 0, random.uniform(-sh, sh)], [0, 1, random.uniform(-sh, sh)]])
            img = cv2.warpAffine(img, M, (V.W, V.H), borderMode=cv2.BORDER_REPLICATE)
        for i, (s, _) in enumerate(self.toasts[-3:]):
            text(img, s, V.W // 2, V.H - S(110) - i * S(30), 0.8, (0, 255, 255), 2, "c")
        if self.paused:
            shade(img, 0, 0, V.W, V.H, (0, 0, 0), 0.55)
            text(img, "PAUSED", V.W // 2, V.H // 2, 2.0, (255, 255, 255), 3, "c", FONT_B)
            text(img, "press P to resume", V.W // 2, V.H // 2 + S(40), 0.7, (220, 220, 220), 1, "c")
        text(img, "%d fps  %dx%d%s" % (self.fps, V.W, V.H, "  MOUSE" if self.mouse_mode else ""), V.W - S(10), V.H - S(10), 0.4, (200, 200, 200), 1, "r")
        if self.debug:
            for i, (nm, c) in enumerate((("MAIN", self.hand_main), ("L", self.hand_lr[0]), ("R", self.hand_lr[1]))):
                text(img, "%s: %s" % (nm, c.dbg if c.present else "-"), S(10), V.H - S(60) + i * S(18), 0.42, (0, 255, 255), 1)
            text(img, "thumb<%.2f fire, >%.2f release   finger ext>%.2f (off<%.2f)  ang>%d (off<%d)" % (
                GESTURE["trig_down"], GESTURE["trig_up"], EXT_RATIO, EXT_RATIO - EXT_HYST, ANG_ON, ANG_OFF),
                 S(10), V.H - S(76), 0.42, (0, 255, 255), 1)
        return img


# ===================== 카메라 / 메인 루프 =====================
def prep_frame(frame, W, H, det_w=640):
    """카메라 프레임을 창 비율로 잘라(크롭) 좌우반전 후 (배경, 검출용) 두 장을 만든다.
    창 비율에 맞춰 먼저 자르므로 손 좌표(0~1)가 화면 좌표와 그대로 대응한다."""
    ch, cw = frame.shape[:2]
    a = W / float(H)
    if cw / float(ch) > a:
        nw = int(ch * a)
        x0 = (cw - nw) // 2
        frame = frame[:, x0:x0 + nw]
    else:
        nh = int(cw / a)
        y0 = (ch - nh) // 2
        frame = frame[y0:y0 + nh]
    frame = cv2.flip(frame, 1)
    bg = cv2.resize(frame, (W, H), interpolation=cv2.INTER_LINEAR)
    if frame.shape[1] > det_w:
        det = cv2.resize(frame, (det_w, int(det_w / a)), interpolation=cv2.INTER_AREA)
    else:
        det = frame
    return bg, det


def open_camera(index=1):
    if sys.platform.startswith("win"):
        backends = ((cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF"), (cv2.CAP_ANY, "ANY"))
    else:
        backends = ((cv2.CAP_ANY, "ANY"),)
    # 카메라 1부터 순차 시도 (기본값: 1번 카메라, 내장/외장 웹캠 모두 대응)
    for idx in range(index, index + 6):
        for be, name in backends:
            cap = cv2.VideoCapture(idx, be)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                # 프레임 읽기 테스트 (최대 5회)
                ok = False
                for _ in range(5):
                    ok, _ = cap.read()
                    if ok:
                        break
                if ok:
                    print("카메라 열림: 인덱스 %d, 백엔드 %s" % (idx, name))
                    return cap
                cap.release()
    return None


def make_landmarker():
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    if not os.path.exists(MODEL_PATH):
        import urllib.request
        print("손 인식 모델 다운로드 중...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    opt = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6, min_tracking_confidence=0.6)
    return mp, vision.HandLandmarker.create_from_options(opt)


def window_size():
    try:
        r = cv2.getWindowImageRect(WIN)
        if r[2] > 100 and r[3] > 100:
            return int(r[2]), int(r[3])
    except Exception:
        pass
    return None


def fit_size(w, h):
    """창 크기 -> 렌더 해상도 (최대/최소 제한, 비율 유지)"""
    if w > RENDER_MAX_W:
        h = int(h * RENDER_MAX_W / float(w))
        w = RENDER_MAX_W
    if w < RENDER_MIN_W:
        h = int(h * RENDER_MIN_W / float(w))
        w = RENDER_MIN_W
    return max(2, w // 2 * 2), max(2, h // 2 * 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mouse", action="store_true", help="마우스로 플레이 (카메라 없이 테스트)")
    ap.add_argument("--cam", type=int, default=1, help="카메라 번호 (기본값: 1)")
    ap.add_argument("--size", default="1280x720", help="처음 창 크기 예: 1280x720")
    ap.add_argument("--fullscreen", action="store_true")
    args = ap.parse_args()
    try:
        iw, ih = [int(v) for v in args.size.lower().split("x")]
    except Exception:
        iw, ih = 1280, 720

    cap, mp, landmarker = None, None, None
    mouse_mode = args.mouse
    game = Game(mouse_mode)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, iw, ih)
    W, H = fit_size(iw, ih)
    V.set(W, H)
    cv2.setMouseCallback(WIN, game.on_mouse)
    fullscreen = False
    if args.fullscreen:
        game.fullscreen_req = True

    if not mouse_mode:
        # --cam 지정 없이도 카메라 0~5 자동 탐색 (기본값: 1번 카메라)
        cap = open_camera(game.cam_index)
        game.cap = cap
        if cap is None:
            print("사용 가능한 웹캠을 찾을 수 없습니다.")
            print("  - Windows 카메라 권한: 설정 > 개인정보 보호 및 보안 > 카메라 > '데스크톱 앱이 카메라에 액세스하도록 허용'을 켬")
            print("  - 특정 카메라 강제 지정: py main.py --cam 1   (또는 --cam 2, --cam 3, --cam 4, --cam 5)")
            print("  - 카메라 없이 마우스로 테스트: py main.py --mouse")
            mouse_mode = True
        else:
            try:
                mp, landmarker = make_landmarker()
            except Exception as e:
                print("MediaPipe 준비 실패 -> 마우스 모드:", e)
                cap.release()
                cap, mouse_mode = None, True

    t0 = prev = time.time()
    last_ts = -1
    frame_i = 0
    print("ESC: 뒤로/종료   F: 전체화면   V: 마우스/카메라   I: 제스처 디버그")

    while not game.quit:
        now = time.time()
        dt = min(0.1, now - prev)
        prev = now
        frame_i += 1
        if frame_i % 6 == 0:
            ws = window_size()
            if ws:
                nw, nh = fit_size(*ws)
                if abs(nw - V.W) > 4 or abs(nh - V.H) > 4:
                    game.resize(nw, nh)
        if game.fullscreen_req:
            game.fullscreen_req = False
            fullscreen = not fullscreen
            cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)

        bg, hands = None, []
        if game.cap is not None:
            ok, frame = game.cap.read()
            if ok:
                bg, det = prep_frame(frame, V.W, V.H)
                if landmarker is not None and not game.mouse_mode:
                    rgb = np.ascontiguousarray(cv2.cvtColor(det, cv2.COLOR_BGR2RGB))
                    ts = int((now - t0) * 1000)
                    if ts <= last_ts:
                        ts = last_ts + 1
                    last_ts = ts
                    res = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                    hands = res.hand_landmarks or []
        game.update(hands, dt, now)
        cv2.imshow(WIN, game.draw(bg, now))
        game.on_key(cv2.waitKey(1) & 0xFF)
        try:
            if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
        except Exception:
            pass

    if isinstance(game.mode, (PvE,)):
        game.mode.leave()
    game.sfx.close()
    if game.cap is not None:
        game.cap.release()
    if landmarker is not None:
        landmarker.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()


