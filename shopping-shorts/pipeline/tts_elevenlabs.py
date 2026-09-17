"""3단계 — ElevenLabs 로 한국어 나레이션을 생성한다.

비용 규칙:
  - 호출 전에 현재 계정의 **남은 무료 크레딧**을 먼저 확인한다.
  - 대본 길이가 남은 크레딧을 넘으면 생성하지 않고 중단 후 보고한다.
  - PAYG / Auto Top Up / 크레딧 한도 확장은 절대 활성화하지 않는다.
    (한도 확장이 이미 켜져 있는 계정이면 경고하고, 그래도 무료 잔량 안에서만 쓴다.)

순수 stdlib 만 사용한다 — 추가 패키지 설치가 필요 없다.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import config
from costguard import CostGuardError, assert_no_paid_features, check_url
from ffprobe_util import audio_duration

API = "https://api.elevenlabs.io/v1"


class TTSUnavailable(RuntimeError):
    """키가 없거나 무료 크레딧이 부족해서 TTS 를 만들 수 없을 때."""


def _request(url: str, *, method: str = "GET", body: bytes | None = None,
             headers: dict[str, str] | None = None, timeout: int = 120):
    check_url(url)
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout)


def _api_key() -> str:
    if not config.ELEVENLABS_API_KEY:
        raise TTSUnavailable(
            "ELEVENLABS_API_KEY 가 설정되어 있지 않습니다. "
            "키를 환경변수로 넣은 뒤 다시 실행하세요."
        )
    return config.ELEVENLABS_API_KEY


def check_credits() -> dict:
    """현재 계정의 크레딧 잔량을 조회한다."""
    try:
        with _request(f"{API}/user/subscription",
                      headers={"xi-api-key": _api_key()}) as resp:
            sub = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise TTSUnavailable(f"크레딧 조회 실패 (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise TTSUnavailable(f"ElevenLabs 에 연결할 수 없습니다: {exc.reason}") from exc

    used = int(sub.get("character_count", 0))
    limit = int(sub.get("character_limit", 0))
    info = {
        "tier": sub.get("tier", "unknown"),
        "used": used,
        "limit": limit,
        "remaining": max(limit - used, 0),
        "resets_at": sub.get("next_character_count_reset_unix"),
        # 켜져 있으면 한도를 넘겼을 때 과금될 수 있는 설정들 — 우리가 켜지는 않는다.
        "extend_enabled": bool(sub.get("can_extend_character_limit")
                               and sub.get("allowed_to_extend_character_limit")),
    }
    return info


def list_voices() -> list[dict]:
    with _request(f"{API}/voices", headers={"xi-api-key": _api_key()}) as resp:
        data = json.loads(resp.read())
    return [{"voice_id": v["voice_id"], "name": v.get("name", "")}
            for v in data.get("voices", [])]


def pick_voice() -> str:
    """설정된 음성 ID 를 쓰거나, 없으면 계정의 첫 번째 음성을 쓴다."""
    if config.ELEVENLABS_VOICE_ID:
        return config.ELEVENLABS_VOICE_ID
    voices = list_voices()
    if not voices:
        raise TTSUnavailable("계정에 사용 가능한 음성이 없습니다.")
    print(f"  ELEVENLABS_VOICE_ID 미설정 → 첫 번째 음성 사용: "
          f"{voices[0]['name']} ({voices[0]['voice_id']})")
    return voices[0]["voice_id"]


def synthesize(text: str, dest: Path) -> dict:
    """대본을 mp3 로 만든다. 무료 잔량이 부족하면 생성하지 않고 예외를 던진다."""
    needed = len(text)
    credits = check_credits()

    print(f"  계정 등급: {credits['tier']}")
    print(f"  크레딧: {credits['used']:,} / {credits['limit']:,} 사용 "
          f"→ 남은 잔량 {credits['remaining']:,}자")
    print(f"  이번 대본: {needed:,}자")

    if credits["extend_enabled"]:
        print("  [주의] 이 계정은 크레딧 한도 확장(과금)이 켜져 있습니다. "
              "이 스크립트는 한도를 넘기지 않으며 결제 설정도 건드리지 않습니다.")

    if needed > credits["remaining"]:
        raise TTSUnavailable(
            f"무료 크레딧 부족 — {needed:,}자가 필요한데 {credits['remaining']:,}자 남았습니다. "
            f"대본을 줄이거나 크레딧이 초기화된 뒤 다시 실행하세요. "
            f"(과금 설정은 켜지 않습니다)"
        )

    voice_id = pick_voice()
    payload = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3},
    }
    assert_no_paid_features(payload)  # 결제 플래그가 섞이지 않았는지 재확인

    try:
        with _request(
            f"{API}/text-to-speech/{voice_id}",
            method="POST",
            body=json.dumps(payload).encode(),
            headers={
                "xi-api-key": _api_key(),
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        ) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise TTSUnavailable(f"TTS 생성 실패 (HTTP {exc.code}): {detail}") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(audio)

    # 요구사항: 파일 존재 여부와 길이를 실제로 확인한다.
    if not dest.exists() or dest.stat().st_size == 0:
        raise TTSUnavailable(f"TTS 파일이 생성되지 않았습니다: {dest}")
    duration = audio_duration(dest)
    if duration <= 0:
        raise TTSUnavailable(f"TTS 파일 길이가 0초입니다: {dest}")

    print(f"  → {dest.name} 생성 ({dest.stat().st_size:,} bytes, {duration:.2f}초)")
    return {"path": str(dest), "duration_s": round(duration, 3),
            "characters": needed, "voice_id": voice_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="ElevenLabs 한국어 TTS")
    parser.add_argument("--check", action="store_true", help="크레딧 잔량만 확인")
    parser.add_argument("--voices", action="store_true", help="사용 가능한 음성 목록")
    parser.add_argument("--text", help="직접 넘긴 문장으로 생성 (미지정 시 script.json 사용)")
    args = parser.parse_args()

    try:
        if args.check:
            print(json.dumps(check_credits(), ensure_ascii=False, indent=2))
            return 0
        if args.voices:
            print(json.dumps(list_voices(), ensure_ascii=False, indent=2))
            return 0

        if args.text:
            text = args.text
        else:
            if not config.SCRIPT_JSON.exists():
                raise TTSUnavailable(
                    f"{config.SCRIPT_JSON} 가 없습니다. 먼저 대본을 확정하세요.")
            script = json.loads(config.SCRIPT_JSON.read_text())
            text = " ".join(b["text"] for b in script["beats"])

        synthesize(text, config.NARRATION_MP3)
        return 0

    except (TTSUnavailable, CostGuardError) as exc:
        print(f"[TTS 중단] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
