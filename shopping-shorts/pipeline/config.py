"""파이프라인 공통 설정과 경로."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 입력 ---------------------------------------------------------------------
# 상업용 최종본에 넣어도 되는, 사용 권한이 확인된 내 영상만 여기에 둔다.
SOURCES_DIR = PROJECT_ROOT / "sources"
# 제3자 레퍼런스(YouTube/TikTok). 분석 전용이며 최종본에 절대 삽입하지 않는다.
REFERENCE_DIR = PROJECT_ROOT / "reference"

# 중간 산출물 ---------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
SOURCE_INDEX = DATA_DIR / "sources.index.json"
REFERENCE_ANALYSIS = DATA_DIR / "reference.analysis.json"
SCRIPT_JSON = DATA_DIR / "script.json"
EDL_JSON = DATA_DIR / "edl.json"

# Remotion 이 staticFile() 로 읽는 위치 ---------------------------------------
PUBLIC_DIR = PROJECT_ROOT / "public"
PUBLIC_CLIPS_DIR = PUBLIC_DIR / "clips"
NARRATION_MP3 = PUBLIC_DIR / "narration.mp3"
THUMBS_DIR = DATA_DIR / "thumbs"

# 출력 ---------------------------------------------------------------------
OUT_DIR = PROJECT_ROOT / "out"
FINAL_MP4 = OUT_DIR / "shopping-short.mp4"

# 영상 규격 -----------------------------------------------------------------
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# 쇼츠 길이 목표 (초). 이 범위를 벗어나면 run.py 가 경고한다.
MIN_DURATION_S = 15
MAX_DURATION_S = 30

# REMIX 규칙: 전체 러닝타임에서 실제 동영상이 차지해야 하는 최소 비율.
MIN_REAL_VIDEO_RATIO = 0.70

# 장면 인덱싱 ---------------------------------------------------------------
# ffmpeg 장면 전환 감지 임계값. 낮출수록 더 잘게 쪼갠다.
SCENE_THRESHOLD = 0.30
# 컷 전환이 없는 통짜 클립은 이 간격(초)으로 강제 분할해서 쓸 수 있는 구간을 만든다.
FALLBACK_SEGMENT_S = 2.5
# 이보다 짧은 구간은 쇼츠 컷으로 쓰기 어려우므로 버린다.
MIN_SCENE_S = 0.8

# TTS ----------------------------------------------------------------------
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
# 한국어 지원 모델. 음성 ID 는 계정에 있는 것으로 바꿔도 된다.
ELEVENLABS_MODEL = "eleven_multilingual_v2"
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()


def ensure_dirs() -> None:
    for d in (SOURCES_DIR, REFERENCE_DIR, DATA_DIR, THUMBS_DIR,
              PUBLIC_DIR, PUBLIC_CLIPS_DIR, OUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
