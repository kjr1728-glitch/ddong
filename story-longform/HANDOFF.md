# 인수인계 — 「사연끝판왕」 팔순잔치 편 (2026-09-19 기준)

이 파일은 클라우드 Claude Code 세션에서 로컬(PC) Claude Code로 작업을 넘기기 위한 것이다.
로컬 세션은 먼저 이 파일과 `PRODUCTION_SPEC.md`를 읽고, 아래 "현재 상태"에서 이어서 진행한다.

## 절대 규칙 (사용자가 직접 정한 것)
- `PRODUCTION_SPEC.md` 30개 항목을 그대로 따른다. 특히: 완전 정지 이미지, Gmarket Sans Bold 62 자막, 배속·피치 변경 금지, 첫 화면 안내 문구 없음, 요청한 부분만 수정, 검수 범위를 과장하지 않는다.
- **Higgsfield는 쓰지 않는다.** (사용자 지시. 이전 세션에서 시험 생성으로 크레딧 12가 쓰였고 사용자가 중단시켰다.)
- 이미지는 **PC의 ComfyUI + FLUX Kontext(GGUF Q4)** 로 만든다 (RTX 3070 Ti 8GB). 무료·자동. `comfy/README.md`.
- 목소리는 **ElevenLabs "Jennie"** (voice_id `z6Kj0hecH20CdetSElRT`, `voice.json`). 1파트 3,000자에 약 0.55달러.
- 무료를 우선하되, 사용자가 이미 승인한 유료는 ElevenLabs 음성뿐이다. 다른 유료 서비스는 먼저 물어본다.
- 사용자와는 한국어로 대화한다. 짧고 직접적으로.

## 작품
- 제목: 시아버지 팔순잔치에서 며느리를 하객 앞에 무릎 꿇린 시누이, 잔치 끝나기 전에 그룹 회장이 며느리 앞에 무릎을 꿇었습니다
- 설계: `works/2026-09-팔순잔치/story.md` (6파트 × 20장면, 인물 6명). 사용자가 "그대로 가자"로 승인.
- 인물 프롬프트: `works/2026-09-팔순잔치/characters/prompts.json` (+ `prompts.md` 설명)

## 현재 상태
| 항목 | 상태 | 파일 |
|---|---|---|
| 1파트 대본 (20문단 = 20장면, 3,028자) | 완료, 사용자에게 전달됨 | `parts/p1/script.txt` |
| 1파트 나레이션 (Jennie, 7분 9초) | 완료. **mp3/wav는 저장소에 없음** (용량). 사용자가 대화창에서 받은 `narration.mp3`를 `parts/p1/`에 넣고 아래 명령으로 wav를 만든다 | `parts/p1/narration.mp3` |
| 1파트 단어 시각 | 완료 (sherpa-onnx 정렬, 일치율 0.919) | `parts/p1/words.json` |
| 1파트 자막 | 완료 (135개, 규격 스타일) | `parts/p1/subs.ass`, `subs.srt` |
| 1파트 장면 시간표 | 완료 (20장면, 16~28초) | `parts/p1/scenes.json` |
| 1파트 장면 프롬프트 | 완료 | `parts/p1/scene_prompts.json` |
| 인물 기준 얼굴 6장 | **미완** — ComfyUI로 생성 후 사용자 승인 필요 | `characters/ref_이름.png` |
| 1파트 장면 이미지 20장 | 미완 | `parts/p1/scenes/001~020.png` |
| 1파트 렌더·검수 | 미완 | `parts/p1/part1.mp4`, `qc_1st.md`, `qc_2nd.md` |
| 2~6파트 대본 | 미완 | `parts/p2~p6/script.txt` |

narration.mp3 → wav 변환 (1파트는 이미 +8dB 정규화된 mp3이므로 게인 없이):
```
ffmpeg -y -i parts\p1\narration.mp3 -ar 48000 -ac 2 parts\p1\narration.wav
```

## 분량 결정 (사용자 미확정)
1파트는 3,028자 → 7분 9초 (약 423자/분). 사용자에게 두 선택지를 냈고 답이 없으면 두 번째로 진행:
1. 파트당 약 7분, 총 약 43분
2. **2파트부터 약 4,200자로 늘려 파트당 10분, 1파트는 그대로** ← 기본값

## 다음 순서 (PC에서)
1. `comfy/README.md` 1~2번: ComfyUI 설치·실행. 사용자 PC에 이미 `C:\ComfyUI`(Wan 2.2용)가 있어 재사용하기로 함.
2. `comfy/README.md` 3번: 기준 얼굴 6장 생성 → 사용자에게 보여 승인.
3. `comfy/README.md` 4번: 1파트 장면 20장 자동 생성(+자동 얼굴 검사). 통과본을 Claude Code가 한 장씩 열어 눈·손·표정 2차 검사, 불합격은 `--only`로 재생성.
4. 렌더와 검수 (README.md 8~11번 명령). 불합격만 고쳐 2차 검수.
5. 1파트 MP4를 사용자에게 보여 승인.
6. 2파트: 대본(4,200자, story.md 2파트 20장면 기준) → 사용자 승인 → `tools/tts_elevenlabs.py`로 음성(words.json 자동) → `make_scenes.py` → 장면 프롬프트 작성 → 이미지 → 자막 → 렌더 → 검수. 3~6파트 동일.
7. `concat_parts.py`로 합본 → `qc.py` 최종 검수 → 사용자에게 전달.

## 도구 요약 (`tools/`, `comfy/`)
- `tts_elevenlabs.py` 대본 → narration.wav/mp3 + words.json + paragraph_times.json (API 키 필요: `.env`의 `ELEVENLABS_API_KEY`)
- `tts_edge.py` 무료 대체 (선희 보이스). 사용자는 Jennie를 택했으므로 기본은 위 도구.
- `align_sherpa.py` 타임스탬프 없는 음성용 정렬 (1파트에 사용). 모델: sherpa-onnx-zipformer-korean-2024-06-24 (GitHub 릴리스에서 다운로드)
- `make_scenes.py` 문단 경계 → scenes.json
- `build_subs.py` → subs.ass/srt (규격 10~13번)
- `render_part.py` → 파트 MP4 (규격 2·3·8·11·21번)
- `qc.py` → 검수 보고서 (규격 24·25·26번)
- `concat_parts.py` → 합본
- `comfy/comfy_pipeline.py` refs / scenes: ComfyUI API 자동 생성 + 얼굴 자동 검사 루프
- `comfy/install_comfyui.ps1`, `comfy/workflows/*.json`

## 대본 작성 규칙 (1파트에서 확정)
- 3인칭 나레이션, "~했습니다" 체, 라디오 사연 낭독 톤. 한 문단 = 한 장면 (빈 줄로 구분).
- 문단은 18~28초 분량(약 120~200자). 대사는 큰따옴표. 숫자는 한글로 (예: 이백 명, 삼십 년).
- TTS가 오독하기 쉬운 표현은 피한다. 각 파트 끝은 다음 파트로 넘어가는 장면에서 끊는다.

## 장면 프롬프트 규칙 (`scene_prompts.json`)
- `{"n": 번호, "who": ["서윤", ...], "prompt": "영어 장면 묘사"}`; 인물은 `{이름}` 자리표시자로 쓰고 얼굴 묘사는 하지 않는다 (참조 이미지가 담당).
- 2인 이상 장면은 파트당 6~8개 이하. 조연·하객은 뒷모습·흐림.
- 16:9, 머리·손 잘림 금지 문구는 파이프라인이 자동으로 붙인다.

## 파일 전달
- 파트 MP4와 최종 MP4는 크므로 저장소에 올리지 않는다 (`.gitignore`). 사용자 PC 폴더에 두고 경로를 알려준다.
- 대본·자막·프롬프트·검수 보고서는 커밋한다. 브랜치: `claude/channel-topic-40s-50s-3p5fmk`.
