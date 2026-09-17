# .claude — 세션 자동 설정

## 스킬 자동 설치 훅

원격 세션(Claude Code on the web)의 컨테이너는 세션이 끝나면 통째로 사라집니다.
`~/.claude/skills/` 에 설치한 스킬도 같이 사라지므로, 웹에서는 "전역 영구 설치"가
원리적으로 불가능합니다.

대신 `hooks/install-skills.sh` 가 **세션이 시작될 때마다** 스킬을 다시 설치해서
영구 설치와 같은 효과를 냅니다.

### 설치되는 것

| 스킬 | 출처 | 용도 |
|------|------|------|
| `watch` | [bradautomates/claude-video](https://github.com/bradautomates/claude-video) | 영상(URL·로컬 파일)을 프레임 + 자막으로 변환해 Claude가 "보게" 함 |
| `remotion-best-practices` | [remotion-dev/skills](https://github.com/remotion-dev/skills) | Remotion 영상 제작 가이드. 하위 11개 스킬을 모두 포함한 라우터 |

`/watch` 실행에 필요한 `ffmpeg` 와 `yt-dlp` 도 없을 때만 함께 설치합니다.

### 동작 방식

1. `CLAUDE_CODE_REMOTE=true` 일 때만 실행됩니다. 로컬 PC에서는 아무것도 하지 않습니다
   (로컬에는 `/plugin` 이나 `npx skills` 로 이미 영구 설치했다고 가정).
2. 두 레포를 `~/.cache/claude-skill-sources/` 에 shallow clone 하고, 이미 있으면 최신으로 갱신합니다.
3. 스킬 폴더를 `~/.claude/skills/` 로 복사합니다. 매 세션 최신 버전이 들어옵니다.
4. 네트워크 실패 등으로 일부가 안 되더라도 경고만 남기고 **세션 시작을 막지 않습니다**.

소요 시간은 의존성이 캐시된 상태에서 약 2초, 처음부터 전부 받는 경우 약 15초입니다.

### 수동 실행

```bash
bash .claude/hooks/install-skills.sh --force
```

`--force` 는 `CLAUDE_CODE_REMOTE` 가드를 무시합니다. 로컬에서 시험해 볼 때 씁니다.

### 스킬 추가·제거

`hooks/install-skills.sh` 하단의 `sync_repo` / `install_skill` 호출을 늘리거나 지우면 됩니다.

```bash
sync_repo <캐시폴더명> <git URL>
install_skill <설치될 스킬 이름> <캐시폴더명/SKILL.md 가 있는 경로>
```

### 참고: Whisper API 키 (선택)

`/watch` 는 자막이 있는 영상은 무료로 처리합니다. 자막이 아예 없는 영상에서만
Whisper 로 음성을 받아쓰는데, 이때 `GROQ_API_KEY` 또는 `OPENAI_API_KEY` 가 필요합니다.
환경 변수로 넣거나 `~/.config/watch/.env` 에 저장하면 됩니다. 없어도 프레임 분석은 됩니다.
