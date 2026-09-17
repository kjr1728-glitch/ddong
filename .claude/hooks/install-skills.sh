#!/usr/bin/env bash
#
# SessionStart hook — 원격(Claude Code on the web) 세션마다 스킬을 자동 설치한다.
#
# 원격 컨테이너는 세션이 끝나면 통째로 사라지므로 ~/.claude/skills 에 넣은 스킬도
# 함께 사라진다. 이 훅이 매 세션 시작 시 다시 설치해서 "영구 설치"와 같은 효과를 낸다.
#
# 설치 대상:
#   watch                     https://github.com/bradautomates/claude-video
#   remotion-best-practices   https://github.com/remotion-dev/skills
#
# 수동 실행(로컬 포함): bash .claude/hooks/install-skills.sh --force
#
set -uo pipefail

# 로컬 PC에서는 스킬을 이미 영구 설치했을 테니 건드리지 않는다.
# 로컬에서도 돌리고 싶으면 --force 를 붙인다.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${1:-}" != "--force" ]; then
  exit 0
fi

CACHE_DIR="${HOME}/.cache/claude-skill-sources"
SKILLS_DIR="${HOME}/.claude/skills"
mkdir -p "$CACHE_DIR" "$SKILLS_DIR"

log()  { echo "[skills] $*"; }
warn() { echo "[skills] WARN: $*" >&2; }

# sync_repo <캐시 폴더명> <git URL>
# 없으면 shallow clone, 있으면 최신으로 갱신. 실패해도 세션을 막지 않는다.
sync_repo() {
  local name="$1" url="$2" dir="$CACHE_DIR/$1"

  if [ -d "$dir/.git" ]; then
    git -C "$dir" fetch --depth 1 -q origin HEAD 2>/dev/null \
      && git -C "$dir" reset --hard -q FETCH_HEAD 2>/dev/null \
      || warn "$name 갱신 실패 — 기존 캐시본을 사용합니다"
  else
    rm -rf "$dir"
    if ! GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 -q "$url" "$dir" 2>/dev/null; then
      warn "$name clone 실패 — 이 스킬은 건너뜁니다"
      return 1
    fi
  fi
  return 0
}

# install_skill <설치될 스킬 이름> <캐시 폴더 기준 소스 경로>
# 심볼릭 링크가 아니라 실제 복사본을 넣는다 (스킬 탐색이 링크를 따라가지 않는 경우 대비).
install_skill() {
  local name="$1" src="$CACHE_DIR/$2"

  if [ ! -f "$src/SKILL.md" ]; then
    warn "$name — SKILL.md 를 찾지 못했습니다 ($src). 건너뜁니다"
    return 1
  fi

  rm -rf "${SKILLS_DIR:?}/$name"
  cp -R "$src" "$SKILLS_DIR/$name" || { warn "$name 복사 실패"; return 1; }
  log "$name 설치됨"
}

# --- 스킬 설치 -------------------------------------------------------------

if sync_repo claude-video https://github.com/bradautomates/claude-video; then
  install_skill watch claude-video/skills/watch
fi

if sync_repo remotion-skills https://github.com/remotion-dev/skills; then
  # remotion-best-practices 는 나머지 11개 Remotion 스킬을 하위 폴더로 모두 품은
  # 라우터 스킬이라, 이것 하나만 설치하면 전부 따라온다.
  install_skill remotion-best-practices remotion-skills/skills/remotion-best-practices
fi

# --- /watch 런타임 의존성 --------------------------------------------------
# ffmpeg/yt-dlp 가 없으면 /watch 는 첫 실행에서 멈춘다. 없을 때만 설치한다.

SUDO=""
[ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"

if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  log "ffmpeg 설치 중..."
  if $SUDO apt-get update -qq >/dev/null 2>&1 &&
     $SUDO apt-get install -y -qq ffmpeg >/dev/null 2>&1; then
    log "ffmpeg 설치됨"
  else
    warn "ffmpeg 설치 실패 — /watch 의 프레임 추출이 동작하지 않습니다"
  fi
fi

if ! command -v yt-dlp >/dev/null; then
  log "yt-dlp 설치 중..."
  # 최신 배포판은 PEP 668 로 시스템 파이썬을 잠가두므로 --break-system-packages 가 먼저다.
  if pip3 install -q --break-system-packages yt-dlp >/dev/null 2>&1 ||
     pip3 install -q yt-dlp >/dev/null 2>&1; then
    log "yt-dlp 설치됨"
  else
    warn "yt-dlp 설치 실패 — /watch 의 URL 다운로드가 동작하지 않습니다"
  fi
fi

# 훅이 실패해도 세션 시작을 막지 않는다.
exit 0
