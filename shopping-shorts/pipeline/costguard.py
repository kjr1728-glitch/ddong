"""추가 결제가 발생하는 API 호출을 코드 레벨에서 차단한다.

이 파이프라인의 비용 규칙은 "모든 API 금지"가 아니라 "추가 결제 금지"다.
허용된 것만 통과시키는 allowlist 방식을 쓴다. 새 외부 호출을 추가할 때는
ALLOWED_HOSTS 에 명시적으로 등록해야 하며, 등록되지 않은 호스트는 예외로 막힌다.
"""

from __future__ import annotations

from urllib.parse import urlparse

# 추가 결제 없이 호출 가능한 호스트만 등록한다.
ALLOWED_HOSTS = {
    # 현재 계정의 무료 크레딧 범위 안에서만 사용한다 (tts_elevenlabs.py 가 잔량을 먼저 확인).
    "api.elevenlabs.io",
}

# 호스트명에 이 문자열이 들어가면 즉시 차단한다. allowlist 를 잘못 넓혔을 때의 2차 방어선.
BLOCKED_SUBSTRINGS = (
    "higgsfield",
    "runwayml",
    "runway.com",
    "klingai",
    "kling.ai",
    "veo",
    "pika.art",
    "lumalabs",
    "sora",
    "remotion.pro",      # Remotion Cloud / Lambda 결제 경로
    "remotionlambda",
)


class CostGuardError(RuntimeError):
    """추가 결제가 발생할 수 있는 호출을 막았을 때 발생한다."""


def check_url(url: str) -> str:
    """허용된 호스트면 url 을 그대로 돌려주고, 아니면 CostGuardError 를 던진다."""
    host = (urlparse(url).hostname or "").lower()

    if not host:
        raise CostGuardError(f"호스트를 파악할 수 없는 URL 입니다: {url!r}")

    for bad in BLOCKED_SUBSTRINGS:
        if bad in host:
            raise CostGuardError(
                f"차단됨 — {host} 는 유료 AI 영상 생성/클라우드 렌더 경로입니다. "
                f"이 파이프라인은 로컬 도구(ffmpeg/Remotion 로컬 렌더)만 사용합니다."
            )

    if host not in ALLOWED_HOSTS:
        raise CostGuardError(
            f"차단됨 — {host} 는 허용 목록에 없습니다. "
            f"추가 결제가 없는 것이 확인되면 costguard.ALLOWED_HOSTS 에 등록하세요. "
            f"현재 허용: {sorted(ALLOWED_HOSTS)}"
        )

    return url


def assert_no_paid_features(payload: dict) -> None:
    """요청 본문에 결제를 켜는 플래그가 섞여 있지 않은지 확인한다."""
    forbidden = {"auto_top_up", "autoTopUp", "enable_payg", "payg", "billing"}
    found = forbidden.intersection(payload)
    if found:
        raise CostGuardError(f"결제 활성화 필드가 요청에 포함되어 있습니다: {sorted(found)}")
