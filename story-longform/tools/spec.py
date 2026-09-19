"""
「사연끝판왕」 제작 규격 상수 (PRODUCTION_SPEC.md 10·11번을 코드로 옮긴 것)

이 파일의 값은 사용자가 확정한 규격이다. 임의로 바꾸지 않는다.
"""
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TOOLS_DIR.parent
FONTS_DIR = PROJECT_DIR / "fonts"
FONT_FILE = FONTS_DIR / "GmarketSansTTFBold.ttf"

# 2. 최종 출력 규격
WIDTH, HEIGHT, FPS = 1920, 1080, 30
AUDIO_RATE, AUDIO_CH, AUDIO_BITRATE = 48000, 2, "192k"

# 10. 자막 ASS 설정 (원문 그대로)
ASS_FONT_NAME = "Gmarket Sans TTF Bold"
ASS_STYLE_LINE = (
    "Style: Default,Gmarket Sans TTF Bold,62,&H00FFFFFF,&H0000FFFF,&H00101010,"
    "&H88000000,0,0,0,0,100,100,0,0,1,3.5,1,2,160,160,112,1"
)
ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{ASS_STYLE_LINE}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# 11. 자막 뒤 배경
BAND_X, BAND_Y, BAND_W, BAND_H = 0, 830, 1920, 250
BAND_OPACITY = 0.23

# 12. 자막 줄바꿈 — 62px 글꼴, 유효 폭 1600px(1920-160-160) 기준 한 줄 최대 글자 수
MAX_CHARS_PER_LINE = 26
MAX_LINES = 2

# 13. 자막 타이밍 — TTS가 알려주는 마지막 음절 종료 시각 뒤에 붙이는 여유(초).
# 음성이 끝나기 전에 자막이 사라지는 일을 막기 위한 값이며, 다음 자막 시작을 넘지 않는다.
SUB_TAIL_SEC = 0.12
