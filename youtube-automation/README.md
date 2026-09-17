# 유튜브 롱폼 자동화 파이프라인 (무료 도구 버전)

vidIQ 없이 무료 도구만으로 구성한 "트렌드 리서치 → 스크립트 → 나레이션 → 영상 합성" 자동화 파이프라인입니다.
업로드까지 포함되어 있지만, 기본 공개 설정은 **비공개**입니다.
확인하지 않은 영상이 자동으로 전체 공개되는 일을 막기 위해서입니다.

## 구성 요소

| 단계 | 도구 | 비용 |
|---|---|---|
| 트렌드/키워드 리서치 | YouTube Data API v3 + Google Trends(pytrends) | 무료 (일일 할당량 내) |
| 스크립트 작성 | Claude Code (직접 대화) 또는 Anthropic API | Claude Code 구독 안에 포함 / API는 종량제 |
| 나레이션(TTS) + 자막 | edge-tts (Microsoft Edge 음성 엔진, 오픈소스 래퍼) | 완전 무료 |
| B-roll 영상 소스 | Pexels API | 무료 (API 키만 발급) |
| 영상 합성 | moviepy 2.x (ffmpeg 내장) | 완전 무료, 오픈소스 |
| 유튜브 업로드 | YouTube Data API v3 (OAuth) | 무료 (할당량 소모) |

## 사전 준비

### 1. Python 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 추가 설치 프로그램 (없음)

영상 인코딩에 쓰는 ffmpeg는 `pip install` 할 때 함께 설치되고,
자막은 Pillow로 직접 그리므로 ImageMagick도 필요 없습니다.
따로 설치하실 프로그램은 없습니다.

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
한글 자막 폰트는 자동으로 찾습니다. 윈도우는 맑은 고딕, 맥은 애플 고딕을 씁니다.
`--font`로 폰트 파일을 직접 지정할 수도 있고, `--no-captions`를 붙이면 자막 없이 뽑습니다.

## 처음 시작하기 (순서대로)

한 번만 해두면 이후에는 명령 한 줄로 돌아갑니다.

**1. 코드 받고 패키지 설치**
```bash
git clone https://github.com/kjr1728-glitch/ddong
cd ddong/youtube-automation
pip install -r requirements.txt
```

**3. 무료 API 키 두 개 발급해서 `.env`에 넣기**
```bash
cp .env.example .env
```
- YouTube Data API v3 키: 트렌드 조회용
- Pexels 키: 배경 영상 다운로드용

**4. 첫 영상 만들어보기 (업로드 없이)**
```bash
python main.py --keyword "미스터리"
```
멈추면 안내된 경로에 스크립트를 저장하고 같은 명령을 다시 실행하세요.
`output/<날짜>_미스터리/final_video.mp4`가 나오면 성공입니다.

처음에는 짧은 스크립트(두세 문장)로 한 번 돌려보길 권합니다.
전체 과정이 문제없이 도는지 5분 안에 확인할 수 있습니다.

**5. 업로드까지 연결하기** (아래 "유튜브 업로드" 참고)

**6. 매일 자동 실행 걸기** (아래 "자동 스케줄링" 참고)

## 유튜브 업로드

업로드는 **API 키로 안 됩니다.** 내 채널에 영상을 올리는 동작이라
OAuth 2.0 인증(구글 계정 로그인)이 따로 필요합니다.

### 최초 1회 설정

1. Google Cloud Console에서 **YouTube Data API v3**가 사용 설정되어 있는지 확인
2. API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → **OAuth 클라이언트 ID**
3. 애플리케이션 유형을 **데스크톱 앱**으로 선택
4. JSON을 내려받아 이 폴더에 `client_secret.json`으로 저장

처음 업로드할 때 브라우저가 열립니다. 업로드할 채널의 구글 계정으로 로그인하면
`token.json`이 만들어지고, 이후에는 로그인 창이 뜨지 않습니다.
`client_secret.json`과 `token.json`은 채널 접근 권한 그 자체입니다.
`.gitignore`에 등록해 두었으니 저장소에 올라가지 않지만, 남에게 주지 마세요.

### 업로드 실행

```bash
# 파이프라인 끝에 바로 업로드 (비공개로 올라감)
python main.py --keyword "미스터리" --upload

# 만들어둔 영상만 따로 업로드
python scripts/youtube_upload.py \
    --video output/2026-01-01_미스터리/final_video.mp4 \
    --script output/2026-01-01_미스터리/script.txt \
    --srt output/2026-01-01_미스터리/narration.srt
```

제목을 안 주면 스크립트 첫 문장에서 만들고, 설명은 스크립트 본문을 넣습니다.
`.srt`가 있으면 자막 트랙으로 같이 등록됩니다.
직접 지정하려면 `--title`, `--tags`를 쓰세요.

### 알아두셔야 할 두 가지

- **기본값이 비공개입니다.** 확인 후 유튜브 스튜디오에서 공개로 바꾸세요.
  처음부터 공개로 올리려면 `--privacy public`을 명시해야 합니다.
- **심사 전에는 공개로 못 올립니다.** 구글은 업로드 권한을 쓰는 앱에 심사를 요구하며,
  심사 전에는 이 앱으로 올린 영상이 비공개로 잠깁니다. 본인 채널에 올려 확인한 뒤
  스튜디오에서 직접 공개로 바꾸는 방식은 심사 없이도 문제없습니다.
  완전 무인 공개까지 원하시면 Google Cloud Console에서 앱 심사를 신청하세요.
- **할당량.** 업로드 1건에 1,600 유닛을 씁니다. 무료 한도가 하루 10,000이라
  트렌드 조회까지 합치면 하루 5건 정도가 현실적인 상한입니다.

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
0 7 * * * cd /path/to/youtube-automation && python main.py --keyword "$(python scripts/pick_topic.py)" --auto-script --upload >> log.txt 2>&1
```
무인 실행에는 `--auto-script`가 필요합니다 (없으면 스크립트 작성 단계에서 멈춥니다).
`--upload`를 빼면 영상 파일만 만들고 업로드는 하지 않습니다.
붙이더라도 비공개로 올라가므로, 아침에 확인하고 공개로 바꾸는 방식이 안전합니다.
결과가 날짜별 폴더로 나뉘므로 매일 돌려도 어제 결과를 덮어쓰지 않습니다.

## 목소리가 안 만들어질 때 (403 오류)

나레이션 단계에서 `WSServerHandshakeError: 403` 이 나오면, 마이크로소프트가
접속 방식을 바꿔서 생기는 알려진 문제입니다. 코드나 설정 잘못이 아닙니다.

먼저 최신 버전으로 올려보세요. 대부분 이걸로 해결됩니다.

```bash
pip install --upgrade edge-tts
```

그래도 같은 오류가 나면 마이크로소프트 쪽 일시적인 장애일 수 있습니다.
과거 사례를 보면 길게는 하루 이틀 걸린 적도 있습니다.
조금 기다렸다가 다시 실행해 보세요. 이미 만들어둔 트렌드 데이터와 스크립트는
그대로 남아 있어서, 같은 명령을 다시 실행하면 나레이션 단계부터 이어집니다.

## 참고
- edge-tts 한국어 음성 목록 확인: `edge-tts --list-voices | grep ko-KR`
  (남성 음성: `ko-KR-InJoonNeural`)
- Pexels는 상업적 이용 가능한 무료 스톡 영상만 제공하므로 저작권 걱정 없이 사용 가능
- YouTube Data API 무료 할당량을 초과하면 다음 날 자정(태평양시간)에 리셋됨
- 영상 합성은 moviepy 2.x 기준입니다. 1.0.3과는 함수 이름이 다르므로 내려쓰지 마세요.
- 세로 쇼츠로 뽑으려면 `scripts/video_synthesis.py`의 `TARGET_SIZE`를 `(1080, 1920)`으로 바꾸세요.
