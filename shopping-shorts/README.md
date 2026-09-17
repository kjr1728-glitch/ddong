# 쇼핑쇼츠 REMIX 파이프라인

여러 개의 **실제 동영상 소스**를 장면 단위로 인덱싱하고, 새 대본에 맞는 구간을
자동으로 골라 15~30초 세로 쇼츠(1080x1920)로 재편집합니다.

제품 이미지를 순서대로 넘기는 슬라이드형 영상이 아닙니다. Remotion 은 영상을
AI 로 생성하지 않고 **실제 컷을 배치·trim·crop·zoom·punch-in·자막·전환** 하는
편집기 역할만 합니다.

## 비용 규칙

추가 결제가 발생하는 호출을 `pipeline/costguard.py` 가 코드 레벨에서 막습니다.

**금지** — Higgsfield, Runway, Kling, Veo, 기타 유료 AI 영상 생성, Remotion Cloud,
PAYG, Auto Top Up.

**허용** — 현재 ElevenLabs 계정의 **무료 크레딧** 범위 안의 TTS, watch, yt-dlp,
ffmpeg, ffprobe, Remotion 로컬 렌더, 로컬 Python/Node 도구.

허용 목록에 없는 호스트는 예외로 차단됩니다. 새 외부 호출을 추가하려면 추가 결제가
없음을 확인한 뒤 `costguard.ALLOWED_HOSTS` 에 명시적으로 등록해야 합니다.

## 저작권 규칙

- `sources/` — 사용 권한이 확인된 **내 영상**. 최종 상업용 영상에 들어갑니다.
- `reference/` — 제3자 YouTube/TikTok 레퍼런스. `rights=reference-only` 로 기록되며
  **분석 전용**입니다. `select_cuts.py` 가 EDL 편입을 거부합니다.

## 사용법

```bash
python3 pipeline/run.py status                  # 현황 점검 (키/크레딧/소스/인덱스)
python3 pipeline/run.py index                   # 1. 소스를 장면 단위로 인덱싱
python3 pipeline/run.py analyze <url> [<url>]   # 2. 레퍼런스를 watch 로 분석
#                                                  3. data/script.json 에 대본 확정
python3 pipeline/run.py tts                     # 4. ElevenLabs 한국어 나레이션
python3 pipeline/run.py cut                     # 5. 대본 ↔ 컷 매칭 → EDL
python3 pipeline/run.py build                   # 6. Remotion 코드 생성
python3 pipeline/run.py render                  # 7. 최종 1080x1920 MP4

python3 pipeline/run.py all                     # 4~7 연속 실행
```

## 단계별 상세

### 1. 장면 인덱싱 — `index_sources.py`

ffmpeg 장면 전환 감지(`scene>0.3`)로 컷을 찾고, 각 구간의 중간 프레임을 썸네일로
뽑습니다. 컷 전환이 없는 통짜 클립은 2.5초 간격으로 강제 분할해 쓸 수 있는 구간을
만듭니다.

```
greeting.mp4  (8.2s, 1920x1080, 컷 0개 → 구간 3개, 권한=owned)
    00:00.0-00:02.5  문 열리는 손
    00:02.5-00:05.0  연화 등장 정면
    00:05.0-00:07.5  책상 앞 연화
```

`label` 과 `tags` 는 비워둔 채 생성됩니다. Claude 가 썸네일을 보고 채우면 6단계
매칭 정확도가 올라갑니다.

### 2. 레퍼런스 분석 — `analyze_reference.py`

watch 스킬로 프레임과 자막을 뽑고, 분석 양식을 만듭니다. Claude 가 프레임을 직접
Read 해서 Hook / 컷 순서 / 컷 길이 / 제품 등장 시점 / 사용 장면 / 결과 장면 /
카피 / TTS / CTA / 자막 / 줌·크롭 / 화면 구성을 채웁니다.

### 3. 대본 — `data/script.json`

`beats` 의 `want` 키워드가 장면의 `label`/`tags` 와 매칭됩니다.

```json
{ "id": "b1", "role": "hook", "want": ["hook", "손"], "text": "요즘 이상하게 일이 안 풀린다면" }
```

### 4. TTS — `tts_elevenlabs.py`

호출 전에 계정의 **남은 무료 크레딧**을 먼저 조회합니다. 대본이 잔량을 넘으면
생성하지 않고 중단 후 보고합니다. 생성 후에는 파일 존재 여부와 길이를 실제로
확인합니다. PAYG / Auto Top Up 은 절대 켜지 않습니다.

```bash
export ELEVENLABS_API_KEY=...
export ELEVENLABS_VOICE_ID=...          # 선택 — 없으면 계정 첫 음성 사용
python3 pipeline/tts_elevenlabs.py --check    # 크레딧 잔량만 확인
python3 pipeline/tts_elevenlabs.py --voices   # 음성 목록
```

### 5. 컷 선택 — `select_cuts.py`

비트의 `want` ↔ 장면의 `label`/`tags` 겹침을 점수로 매기고, 길이 적합도와 크롭
손실을 반영하며, 이미 쓴 구간에 감점을 줘 같은 그림 반복을 피합니다. 나레이션이
있으면 비트별 글자 수에 비례해 화면 시간을 나눕니다.

### 6. 코드 생성 — `gen_timeline.py`

Remotion 은 편집 가능한 컷을 `.map()` 으로 만들면 안 되므로, **하드코딩된 TSX 를
생성**합니다. Studio 타임라인에서 컷을 직접 드래그해 수정할 수 있습니다.

전환(크로스페이드)은 두 컷이 겹쳐 재생되어 전체 길이를 줄이므로, 자막 타이밍도
겹침을 반영한 실제 시작 프레임 기준으로 다시 계산합니다.

### 7. 렌더 — `run.py render`

**가드** (통과 못 하면 렌더하지 않습니다):

| 조건 | 동작 |
|---|---|
| `narration.mp3` 없음 | 최종 렌더 **거부**. 음성 없는 영상을 최종본으로 내보내지 않습니다 |
| 실사 비율 < 70% | 렌더 **거부** |
| 길이가 15~30초 밖 | 경고만 하고 진행 |

화면만 확인하려면 `render --draft` 를 씁니다. 파일명에 `NO-AUDIO` 가 붙고 최종본
경로에 저장되지 않습니다.

## 파일 구조

```
pipeline/
  costguard.py           추가 결제 호출 차단 (allowlist)
  config.py              경로·규격·임계값
  ffprobe_util.py        ffmpeg/ffprobe 래퍼
  index_sources.py       1. 장면 인덱싱
  analyze_reference.py   2. 레퍼런스 분석 (watch)
  tts_elevenlabs.py      4. 무료 크레딧 확인 + 한국어 TTS
  select_cuts.py         5. 대본 ↔ 컷 매칭 → EDL
  gen_timeline.py        6. EDL → 하드코딩 TSX 생성
  run.py                 오케스트레이터 + 렌더 가드

src/
  VideoCut.tsx           한 컷 (cover 채움 + 재프레이밍 + punch-in)
  Subtitles.tsx          자막
  CtaCard.tsx            CTA 오버레이
  ShoppingShort.tsx      최종 컴포지션
  Root.tsx               컴포지션 등록
  generated/             gen_timeline.py 가 생성 — 직접 고치지 마세요

data/
  sources.index.json     장면 인덱스
  reference.analysis.json 레퍼런스 분석
  script.json            한국어 대본
  edl.json               편집 결정 목록
```

## 현재 상태

`sources/` 에 들어 있는 것은 이 저장소의 사주 서비스 클립 2개(합계 17.3초)이고,
`data/script.json` 은 **파이프라인 검증용 샘플 대본**입니다. 실제 제품 영상과
대본으로 교체해서 쓰세요.

검증 완료: 6컷 매칭 → 코드 생성 → 1080x1920 MP4 렌더(13.07초, 실사 100%).
