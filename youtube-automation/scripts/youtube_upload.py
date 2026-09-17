"""
유튜브 업로드 — YouTube Data API v3 (OAuth 2.0)

주의: 업로드는 API 키로 안 됩니다. 내 채널에 글을 쓰는 동작이라
OAuth 2.0 인증(구글 계정 로그인)이 따로 필요합니다.
처음 한 번만 브라우저가 열리고, 이후에는 저장된 토큰을 재사용합니다.

안전장치: 기본 공개 설정은 '비공개(private)'입니다.
확인도 안 한 영상이 자동으로 전체 공개되는 일을 막기 위해서입니다.
공개로 올리려면 --privacy public을 명시적으로 지정하세요.

사용법:
    python scripts/youtube_upload.py --video output/.../final_video.mp4 \
        --title "제목" --script output/.../script.txt --srt output/.../narration.srt
"""
import argparse
import os
import random
import re
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# 업로드와 자막 등록에 필요한 권한
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CLIENT_SECRET = os.path.join(PROJECT_ROOT, "client_secret.json")
DEFAULT_TOKEN = os.path.join(PROJECT_ROOT, "token.json")

# 일시적인 서버 오류에만 재시도합니다. 권한/할당량 오류는 재시도해도 소용없습니다.
RETRIABLE_STATUS = (500, 502, 503, 504)
MAX_RETRIES = 5

MAX_TITLE_LEN = 100
MAX_DESCRIPTION_LEN = 5000


def get_credentials(client_secret_path: str, token_path: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except ValueError:
            print("[경고] 저장된 토큰을 읽을 수 없어 다시 로그인합니다.")
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        print("토큰 갱신 중...")
        creds.refresh(Request())
    else:
        if not os.path.exists(client_secret_path):
            raise SystemExit(
                f"OAuth 클라이언트 파일이 없습니다: {client_secret_path}\n\n"
                "Google Cloud Console에서 만들어 받아주세요:\n"
                "  API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기\n"
                "  → OAuth 클라이언트 ID → 애플리케이션 유형 '데스크톱 앱'\n"
                "  → JSON 다운로드 후 위 경로에 client_secret.json으로 저장\n"
            )
        print("브라우저에서 구글 계정 로그인 창이 열립니다. 업로드할 채널의 계정으로 로그인하세요.")
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    # 토큰은 채널 접근 권한 그 자체이므로 본인만 읽도록 제한합니다.
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    print(f"인증 정보 저장: {token_path} (다음부터는 로그인 창이 뜨지 않습니다)")

    return creds


def strip_tags(text: str) -> str:
    return re.sub(r"\[SECTION:.*?\]", "", text).strip()


def derive_title(script_path: str, fallback: str) -> str:
    """제목을 따로 안 줬을 때 스크립트 첫 문장에서 만들어본다"""
    if not script_path or not os.path.exists(script_path):
        return fallback[:MAX_TITLE_LEN]

    with open(script_path, "r", encoding="utf-8") as f:
        text = strip_tags(f.read())

    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    sentence = re.split(r"(?<=[.!?？！])\s", first)[0].strip() if first else ""
    title = sentence or fallback
    return title[:MAX_TITLE_LEN]


def build_description(script_path: str, description: str, description_file: str) -> str:
    if description:
        return description[:MAX_DESCRIPTION_LEN]

    if description_file and os.path.exists(description_file):
        with open(description_file, "r", encoding="utf-8") as f:
            return f.read()[:MAX_DESCRIPTION_LEN]

    if script_path and os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            body = strip_tags(f.read())
        return body[:MAX_DESCRIPTION_LEN]

    return ""


def upload_video(youtube, args, title: str, description: str) -> str:
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [],
            "categoryId": args.category,
            "defaultLanguage": args.language,
            "defaultAudioLanguage": args.language,
        },
        "status": {
            "privacyStatus": args.privacy,
            # 아동용 여부는 반드시 선언해야 합니다. 기본은 '아동용 아님'입니다.
            "selfDeclaredMadeForKids": args.made_for_kids,
        },
    }

    media = MediaFileUpload(
        args.video, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/*"
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  업로드 중... {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS:
                retry += 1
                if retry > MAX_RETRIES:
                    raise SystemExit("업로드에 반복 실패했습니다. 잠시 후 다시 시도해 주세요.")
                wait = min(2 ** retry, 60) + random.random()
                print(f"  [일시 오류 {e.resp.status}] {wait:.1f}초 후 재시도 ({retry}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            if e.resp.status == 403:
                raise SystemExit(
                    "업로드가 거부되었습니다 (403).\n"
                    "일일 할당량을 초과했거나(업로드 1건에 1,600 유닛 소모, 무료 한도 10,000),\n"
                    "해당 계정에 업로드 권한이 없을 수 있습니다."
                )
            raise

    return response["id"]


def upload_caption(youtube, video_id: str, srt_path: str, language: str):
    """자막 파일을 영상에 붙인다. 실패해도 영상 업로드 자체는 이미 끝난 상태다."""
    try:
        youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": "자동 생성 자막",
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(srt_path, mimetype="application/octet-stream"),
        ).execute()
        print(f"자막 등록 완료: {os.path.basename(srt_path)}")
    except HttpError as e:
        print(f"[경고] 자막 등록 실패 (영상은 이미 올라갔습니다): {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="업로드할 영상 파일")
    parser.add_argument("--title", default=None, help="영상 제목 (생략 시 스크립트 첫 문장에서 생성)")
    parser.add_argument("--script", default=None, help="제목/설명을 만들 때 참고할 스크립트")
    parser.add_argument("--description", default=None)
    parser.add_argument("--description-file", default=None)
    parser.add_argument("--tags", default=None, help="쉼표로 구분된 태그")
    parser.add_argument("--srt", default=None, help="함께 등록할 자막 파일")
    parser.add_argument(
        "--privacy",
        default="private",
        choices=["private", "unlisted", "public"],
        help="기본값 private. 확인 없이 전체 공개되는 것을 막기 위한 안전장치입니다.",
    )
    parser.add_argument("--category", default="22", help="유튜브 카테고리 ID (기본 22: 인물/블로그)")
    parser.add_argument("--language", default="ko")
    parser.add_argument(
        "--made-for-kids",
        action="store_true",
        help="아동용 콘텐츠로 신고 (기본: 아동용 아님)",
    )
    parser.add_argument("--client-secret", default=DEFAULT_CLIENT_SECRET)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    args = parser.parse_args()

    if not os.path.exists(args.video):
        raise SystemExit(f"영상 파일이 없습니다: {args.video}")

    title = args.title or derive_title(args.script, os.path.basename(args.video))
    description = build_description(args.script, args.description, args.description_file)

    creds = get_credentials(args.client_secret, args.token)
    youtube = build("youtube", "v3", credentials=creds)

    size_mb = os.path.getsize(args.video) / (1024 * 1024)
    print(f"\n업로드 시작: {args.video} ({size_mb:.1f}MB)")
    print(f"  제목: {title}")
    print(f"  공개 설정: {args.privacy}")

    video_id = upload_video(youtube, args, title, description)
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n업로드 완료: {url}")

    if args.srt and os.path.exists(args.srt):
        upload_caption(youtube, video_id, args.srt, args.language)

    if args.privacy == "private":
        print(
            "\n지금은 비공개 상태입니다. 영상을 확인한 뒤 유튜브 스튜디오에서 공개로 바꾸세요.\n"
            "처음부터 공개로 올리려면 --privacy public을 붙이면 됩니다."
        )


if __name__ == "__main__":
    main()
