# 유튜브 롱폼 자동화 파이프라인 (무료 도구 버전)

vidIQ 없이 무료 도구만으로 구성한 "트렌드 리서치 → 스크립트 → 나레이션 → 영상 합성" 자동화 파이프라인입니다.
업로드는 포함하지 않습니다 (직접 검토 후 수동 업로드 권장).

## 구성 요소

| 단계 | 도구 | 비용 |
|---|---|---|
| 트렌드/키워드 리서치 | YouTube Data API v3 + Google Trends(pytrends) | 무료 (일일 할당량 내) |
| 스크립트 작성 | Claude Code (직접 대화) 또는 Anthropic API | Claude Code 구독 안에 포함 / API는 종량제 |
| 나레이션(TTS) + 자막 | edge-tts (Microsoft Edge 음성 엔진, 오픈소스 래퍼) | 완전 무료 |
| B-roll 영상 소스 | Pexels API | 무료 (API 키만 발급) |
| 영상 합성 | ffmpeg + moviepy | 완전 무료, 오픈소스 |

## 사전 준비

### 1. Python 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. ffmpeg + ImageMagick 설치 (시스템 레벨)
```bash
# Mac
brew install ffmpeg imagemagick
# Ubuntu/Debian
sudo apt install ffmpeg imagemagick
# Windows: https://ffmpeg.org/download.html 에서 다운로드 후 PATH 등록
```
ImageMagick은 영상에 자막을 태워 넣을 때만 필요합니다. 없으면 자막 없이 영상만
렌더링되고, 자막 파일(.srt)은 따로 남으니 유튜브 업로드 시 자막으로 올리면 됩니다.

### 3. 무료 API 키 발급 (둘 다 무료)
- **YouTube Data API v3 키**: Google Cloud Console → API 및 서비스 → 사용 설정 → "YouTube Data API v3" → 사용자 인증 정보에서 API 키 생성
  (일일 할당량 10,000 유닛 무료 — 검색/리스트 조회로 충분히 사용 가능)
- **Pexels API 키**: https://www.pexels.com/api/ 에서 가입 후 즉시 무료 발급

### 4. `.env` 파일 만들기
`.env.example`을 복사해서 `.env`로 만들고 키 입력:
```bash
cp .env.example .env
```

## 사용 방법

### 전체 파이프라인 한 번에 (권장)
```bash
python main.py --keyword "미스터리"
```
실행하면 `output/<날짜>_<키워드>/` 폴더를 만들고 그 안에 결과를 모읍니다.
2단계(스크립트 작성)에서 한 번 멈추고, 어느 경로에 스크립트를 저장하면 되는지
알려줍니다. 저장한 뒤 같은 명령을 다시 실행하면 끝난 단계는 건너뛰고 이어서 진행합니다.

사람 개입 없이 끝까지 돌리려면 (Anthropic API 종량 과금):
```bash
python main.py --keyword "미스터리" --auto-script
```

### 단계별로 실행하기

**1단계: 트렌드 리서치**
```bash
python scripts/trend_research.py --keyword "미스터리" --region KR
```
→ 관련 키워드, 경쟁 채널의 인기 영상 목록을 `output/trends.json`에 저장

**2단계: 스크립트 작성**
- 추천: `trends.json` 내용을 보고 **Claude Code에게 직접 요청**
  ("이 트렌드 데이터로 5분 분량 롱폼 스크립트 써줘")
  → API 비용 없이, Claude Code 구독만으로 가능
- 또는 Anthropic API 키가 있다면 `scripts/script_writer.py` 사용 (선택사항, 종량 과금)

이때 **문단마다 아래 형식의 태그를 넣어달라고 요청하세요.**
```
[SECTION: 밤하늘의 비밀 | night sky stars timelapse]
```
파이프(`|`) 뒤의 영어 키워드가 배경 영상 검색어로 그대로 쓰이기 때문에,
이 태그만 있으면 4단계에서 사람이 검색어를 입력할 필요가 없습니다.

**3단계: 나레이션 + 자막 생성**
```bash
python scripts/narration.py --script output/script.txt --voice ko-KR-SunHiNeural
```
→ `narration.mp3`와 함께 `narration.srt` 생성 (완전 무료, API 키 불필요)

자막 타이밍은 edge-tts가 알려주는 실제 단어 발화 시각을 기준으로 계산합니다.
영상 길이를 문장 수로 균등 분할하는 방식보다 훨씬 정확하게 맞습니다.

**4단계: B-roll 영상 수집**
```bash
# 스크립트의 [SECTION: ... | keywords] 태그에서 검색어 자동 추출
python scripts/broll_fetcher.py --from-script output/script.txt --count 5

# 또는 직접 지정
python scripts/broll_fetcher.py --keywords "night city,mystery,dark forest" --count 10
```
→ `assets/broll/`에 무료 라이선스 영상 다운로드

**5단계: 영상 합성**
```bash
python scripts/video_synthesis.py --narration output/narration.mp3 \
    --broll-dir assets/broll --script output/script.txt
```
→ `final_video.mp4` 생성 (나레이션 + b-roll + 자막)

같은 이름의 `.srt`가 있으면 그 타이밍을 쓰고, 없으면 문장 균등 분할로 대체합니다.
한글 자막 폰트는 시스템에서 자동으로 찾으며, `--font`로 직접 지정할 수도 있습니다.
자막 없이 뽑으려면 `--no-captions`를 붙이세요.

## 자동 스케줄링 (완전 자동화)

`topics.txt`에 주제를 한 줄에 하나씩 적어두면, `pick_topic.py`가 매 실행마다
다음 주제를 하나씩 꺼내 씁니다 (끝에 닿으면 처음으로 돌아갑니다).

```bash
python scripts/pick_topic.py          # 다음 주제를 꺼내 쓰고 기록
python scripts/pick_topic.py --peek   # 기록하지 않고 미리보기
python scripts/pick_topic.py --list   # 전체 목록과 현재 위치
```

macOS/Linux — crontab:
```bash
crontab -e
# 매일 오전 7시 실행
0 7 * * * cd /path/to/youtube-automation && python main.py --keyword "$(python scripts/pick_topic.py)" --auto-script >> log.txt 2>&1
```
무인 실행에는 `--auto-script`가 필요합니다 (없으면 스크립트 작성 단계에서 멈춥니다).
결과가 날짜별 폴더로 나뉘므로 매일 돌려도 어제 결과를 덮어쓰지 않습니다.

## 참고
- edge-tts 한국어 음성 목록 확인: `edge-tts --list-voices | grep ko-KR`
  (남성 음성: `ko-KR-InJoonNeural`)
- Pexels는 상업적 이용 가능한 무료 스톡 영상만 제공하므로 저작권 걱정 없이 사용 가능
- YouTube Data API 무료 할당량을 초과하면 다음 날 자정(태평양시간)에 리셋됨
- `moviepy 1.0.3`은 Pillow 10에서 삭제된 API를 쓰기 때문에 `requirements.txt`가
  Pillow를 9.x로 고정해 둡니다. 임의로 올리면 합성 단계에서 멈춥니다.
- 세로 쇼츠로 뽑으려면 `scripts/video_synthesis.py`의 `TARGET_SIZE`를 `(1080, 1920)`으로 바꾸세요.
