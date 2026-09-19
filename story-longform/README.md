# 「사연끝판왕」 장편 사연 영상 — Claude Code 제작 안내

`PRODUCTION_SPEC.md`의 30개 규격을 그대로 따르는 제작 도구와 진행 순서입니다.
주제는 `TOPIC_RESEARCH.md`의 후보 중에서 고르거나 새로 정합니다.

## 준비물 (집 PC, 한 번만)

1. **Python 3.10 이상** (설치 시 "Add to PATH" 체크)
2. **FFmpeg** — https://www.gyan.dev/ffmpeg/builds/ 에서 `ffmpeg-release-essentials.zip` 받아 풀고
   `bin` 폴더를 PATH에 등록. 명령창에서 `ffmpeg -version`이 뜨면 됨.
3. **Claude Code** 설치 후 이 저장소를 받는다.
   ```
   git clone https://github.com/kjr1728-glitch/ddong
   cd ddong\story-longform
   pip install -r requirements.txt
   ```
4. **폰트** `fonts/GmarketSansTTFBold.ttf` — 저장소에 포함돼 있음. 렌더는 이 파일을 직접 읽으므로 Windows에 설치할 필요 없음.
5. **이미지 생성 도구** — 그래픽카드가 있으면 ComfyUI(무료), 없으면 Gemini 앱(무료, 수동). 결정되면 Claude Code에 그래픽카드 모델명을 알려주면 설치 스크립트를 만들어 준다.
6. **목소리** — `voice.json`에 확정 보이스(Jennie - Narrational)가 적혀 있음. 바꾸려면 voice_id만 수정.
7. **PC 점검** — `python tools/check_pc.py` 결과를 Claude Code에 붙여넣으면 ComfyUI 상태에 맞춰 다음 단계를 잡아 준다.

## 폴더 구조 (작품 하나 = 폴더 하나)

```
story-longform/
  works/2026-09-사연제목/
    story.md            전체 이야기 설계 (60분, 6파트, 인물표)
    characters/         인물별 기준 얼굴 이미지 + 프롬프트
    parts/p1 ~ p6/
      script.txt        파트 대본 (나레이션 그대로)
      narration.wav     TTS 음성
      words.json        단어별 발화 시각 [{"word","start","end"}]
      scenes.json       장면 목록 [{"image","start","end"}]
      scenes/001.png … 장면 이미지 (16:9, 1920×1080 이상)
      subs.ass / .srt   자막 (build_subs.py가 생성)
      part1.mp4         파트 렌더 결과
      qc_1st.md / qc_2nd.md   1차·2차 검수 결과
    final/final.mp4     6파트 합본
```

## 진행 순서 (Claude Code에 시킬 말 그대로)

각 단계는 Claude Code 대화창에 아래처럼 말하면 된다. 규격 파일을 먼저 읽게 하는 것이 핵심이다.

**0. 시작**
> `story-longform/PRODUCTION_SPEC.md`를 읽고, 「(주제)」로 새 작품을 시작해. `works/` 아래에 폴더를 만들어.

**1~2. 이야기 설계와 6파트 대본**
> 60분 분량 전체 이야기를 설계하고 `story.md`에 저장해. 등장인물은 5명 이내, 2인 이상 장면은 꼭 필요한 곳만.
> 승인하면 파트 1부터 6까지 대본을 `parts/pN/script.txt`로 써. 한 파트 약 10분(Jennie 기준 약 4,200자, 실측 423자/분).

**3. 인물 기준 얼굴**
> 주요 인물마다 기준 얼굴 프롬프트를 `characters/`에 만들어. (ComfyUI면 여기서 자동 생성, Gemini면 프롬프트를 복사해서 직접 생성 후 저장)

**4~5. 장면 분할과 이미지**
> 파트 1 대본을 약 30초 단위 장면으로 나눠 `scenes.json`과 장면별 이미지 프롬프트를 만들어. 이미지가 준비되면 `scenes/`에 번호대로 저장.
> Claude Code가 이미지를 한 장씩 열어 눈·손·얼굴 일관성을 검사하고 불합격 목록을 준다 → 해당 장면만 재생성.

**6. 내레이션**
> `voice.json`의 보이스로 파트 1 대본을 TTS로 만들어 `narration.wav`와 `words.json`을 저장해.
```
python tools/tts_elevenlabs.py --script parts/p1/script.txt --out parts/p1
python tools/make_scenes.py --script parts/p1/script.txt --words parts/p1/words.json --audio parts/p1/narration.wav --out parts/p1/scenes.json
```
(타임스탬프 없는 음성이면 `tools/align_sherpa.py`로 대본과 정렬)

**7. 자막**
```
python tools/build_subs.py --script parts/p1/script.txt --words parts/p1/words.json --out parts/p1/subs.ass
```

**8. 파트 렌더**
```
python tools/render_part.py --scenes parts/p1/scenes.json --audio parts/p1/narration.wav --subs parts/p1/subs.ass --out parts/p1/part1.mp4
```

**9~11. 검수 → 수정 → 재검수**
```
python tools/qc.py --video parts/p1/part1.mp4 --subs parts/p1/subs.ass --scenes parts/p1/scenes.json --report parts/p1/qc_1st.md
```
불합격 항목만 고친 뒤 다시 렌더하고 `--report parts/p1/qc_2nd.md`로 2차 검수.
qc.py는 규격·디코딩·검은 화면·프레임 수·싱크·정지 여부·자막 겹침을 검사한다.
얼굴·눈·손과 실제 청취는 검사하지 않으며 보고서에 그렇게 적힌다.

**12~13. 합본과 최종 검수**
```
python tools/concat_parts.py --parts parts/p1/part1.mp4 parts/p2/part2.mp4 parts/p3/part3.mp4 parts/p4/part4.mp4 parts/p5/part5.mp4 parts/p6/part6.mp4 --out final/final.mp4
python tools/qc.py --video final/final.mp4 --report final/qc_final.md
```

## voice.json 예시

```json
{
  "provider": "elevenlabs",
  "voice_id": "여기에_보이스_ID",
  "model_id": "eleven_multilingual_v2",
  "stability": 0.5,
  "similarity_boost": 0.75,
  "speed": 1.0,
  "pitch_shift": false
}
```
`speed`는 1.0 고정 (규격 16번). `pitch_shift`는 false 고정 (규격 15번).

## 규격이 코드에 어떻게 박혀 있는지

| 규격 | 위치 |
|---|---|
| 2번 출력 규격 | `tools/spec.py`, `render_part.py`의 인코딩 옵션 |
| 3번 완전 정지 | `render_part.py`는 확대·이동 필터를 쓰지 않음. `qc.py`가 장면 첫/끝 프레임 SSIM으로 검증 |
| 8번 잘림 금지 | `render_part.py`가 16:9가 아닌 이미지를 거부 (잘라 쓰지 않음) |
| 9·10번 폰트·ASS | `spec.py`의 `ASS_STYLE_LINE` 원문 그대로, `fonts/`의 TTF를 직접 지정 |
| 11번 자막 띠 | `spec.py` BAND_* 값, `render_part.py` drawbox |
| 12번 줄바꿈 | `build_subs.py` 의미 단위 분리 (공백에서만, 26자, 2줄) |
| 13번 타이밍 | `build_subs.py` 단어 시각 기반, 다음 자막을 넘지 않음 |
| 21번 안내 문구 없음 | 렌더에 Notice 코드 자체가 없음 |
| 25번 합본 검수 | `qc.py` |
| 26번 정직한 보고 | `qc.py` 보고서의 "검사하지 않은 것" 항목 |

## 검증 기록

2026-09-19, 이 저장소 환경에서 두 장면짜리 테스트 파트를 렌더해 확인한 것:
1920×1080 30fps H.264 yuv420p, AAC 48kHz 2ch, faststart, 디코딩 오류 0, 프레임 수 일치,
Gmarket Sans Bold 62 자막이 참고 영상과 같은 위치·크기·띠로 표시됨.
