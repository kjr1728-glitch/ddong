# 이 저장소에서 Claude Code가 지킬 것

- 사용자와는 **한국어**로 대화한다.
- 장편 사연 영상 작업은 `story-longform/` 아래에서 한다. 시작할 때 반드시 다음 두 파일을 읽는다:
  1. `story-longform/HANDOFF.md` — 지금까지의 결정과 현재 상태, 다음 순서
  2. `story-longform/PRODUCTION_SPEC.md` — 사용자가 확정한 제작 규격 30개 (임의 변경 금지)
- 유료 서비스는 사용자가 승인한 ElevenLabs 음성만 쓴다. Higgsfield는 쓰지 않는다. 다른 유료는 먼저 묻는다.
- 검수 결과를 과장하지 않는다. 검사한 범위와 못 한 범위를 구분해 보고한다 (규격 26번).
- 사용자가 요청한 부분만 고친다. 이미 승인된 요소는 건드리지 않는다 (규격 22번).
- 큰 미디어 파일(mp4, wav, mp3, png)은 커밋하지 않는다. `story-longform/.gitignore` 참고.
- `youtube-automation/`은 별도의 롱폼 자동화 파이프라인(다른 채널용)이다. 사연 영상과 섞지 않는다.
