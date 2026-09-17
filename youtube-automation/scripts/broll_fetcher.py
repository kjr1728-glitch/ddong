"""
B-roll 영상 수집 — Pexels 무료 API (상업적 이용 가능한 무료 라이선스)

스크립트의 [SECTION: 소주제 | english keywords] 태그에서 검색어를 자동으로
뽑아올 수 있어서, 사람이 매번 영어 키워드를 입력하지 않아도 됩니다.

사용법:
    python broll_fetcher.py --keywords "night city,mystery,dark forest" --count 10
    python broll_fetcher.py --from-script output/script.txt --count 5
"""
import argparse
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

SECTION_PATTERN = re.compile(r"\[SECTION:\s*(.*?)\s*\]")


def keywords_from_script(script_path: str) -> list:
    """
    [SECTION: 밤하늘의 비밀 | night sky stars] → "night sky stars"
    구분자가 없으면 태그 전체를 그대로 검색어로 씁니다.
    Pexels는 영어 검색만 잘 되므로, 한글만 있는 태그는 건너뜁니다.
    """
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    keywords = []
    for tag in SECTION_PATTERN.findall(content):
        candidate = tag.split("|")[-1].strip() if "|" in tag else tag.strip()
        # 한글이 섞여 있으면 Pexels 검색이 사실상 실패하므로 제외
        if not candidate or re.search(r"[가-힣]", candidate):
            continue
        if candidate.lower() not in [k.lower() for k in keywords]:
            keywords.append(candidate)

    return keywords


def search_and_download(keyword: str, count: int, out_dir: str) -> list:
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": keyword, "per_page": min(count, 80), "orientation": "landscape"}

    resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    videos = resp.json().get("videos", [])

    if not videos:
        print(f"  [경고] '{keyword}' 검색 결과 없음 — 건너뜁니다.")
        return []

    os.makedirs(out_dir, exist_ok=True)
    downloaded = []

    for i, video in enumerate(videos):
        files = sorted(video["video_files"], key=lambda f: f.get("width", 0), reverse=True)
        if not files:
            continue

        # 1920 이하 중 가장 큰 화질을 고르고, 없으면 가장 작은 것
        hd_files = [f for f in files if f.get("width", 0) <= 1920]
        target = hd_files[0] if hd_files else files[-1]

        safe_keyword = re.sub(r"[^\w]+", "_", keyword).strip("_") or "broll"
        filename = os.path.join(out_dir, f"{safe_keyword}_{i}.mp4")

        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            print(f"  이미 있음, 건너뜀: {filename}")
            downloaded.append(filename)
            continue

        try:
            with requests.get(target["link"], stream=True, timeout=60) as video_resp:
                video_resp.raise_for_status()
                with open(filename, "wb") as f:
                    for chunk in video_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
        except requests.RequestException as e:
            print(f"  [경고] 다운로드 실패, 건너뜀: {e}")
            # 중간까지 받다 만 파일은 지워야 합성 단계에서 깨지지 않는다
            if os.path.exists(filename):
                os.remove(filename)
            continue

        downloaded.append(filename)
        print(f"  다운로드 완료: {filename}")

    return downloaded


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--keywords", help="쉼표로 구분된 영어 키워드 (예: night city,forest)")
    source.add_argument(
        "--from-script",
        help="스크립트 파일의 [SECTION: ... | english keywords] 태그에서 검색어 자동 추출",
    )
    parser.add_argument("--count", type=int, default=5, help="키워드당 다운로드 개수")
    parser.add_argument("--output-dir", default="assets/broll")
    args = parser.parse_args()

    if not PEXELS_API_KEY:
        raise SystemExit(".env 파일에 PEXELS_API_KEY를 설정하세요.")

    if args.from_script:
        keywords = keywords_from_script(args.from_script)
        if not keywords:
            raise SystemExit(
                f"{args.from_script}에서 영어 b-roll 키워드를 찾지 못했습니다.\n"
                "스크립트의 섹션 태그를 [SECTION: 소주제 | english keywords] 형식으로 써주세요.\n"
                "또는 --keywords로 직접 지정하세요."
            )
        print(f"스크립트에서 키워드 {len(keywords)}개 추출: {', '.join(keywords)}")
    else:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
        if not keywords:
            raise SystemExit("--keywords에 유효한 키워드가 없습니다.")

    all_files = []
    for kw in keywords:
        print(f"'{kw}' 검색 중...")
        try:
            all_files.extend(search_and_download(kw, args.count, args.output_dir))
        except requests.RequestException as e:
            print(f"  [경고] '{kw}' 검색 실패, 건너뜁니다: {e}")

    if not all_files:
        raise SystemExit("영상을 하나도 받지 못했습니다. API 키와 네트워크를 확인하세요.")

    print(f"\n총 {len(all_files)}개 영상 준비 완료 → {args.output_dir}")


if __name__ == "__main__":
    main()
