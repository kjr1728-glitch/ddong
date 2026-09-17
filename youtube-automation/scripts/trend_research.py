"""
트렌드/키워드 리서치 (무료)
- YouTube Data API v3: 키워드로 인기 영상 검색, 조회수/경쟁 파악
- Google Trends (pytrends): 검색 관심도 추이, 연관 키워드

사용법:
    python trend_research.py --keyword "미스터리" --region KR
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pytrends.request import TrendReq

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


def search_youtube_videos(keyword: str, region: str, max_results: int = 15):
    """키워드 관련 최근 인기 영상 검색 (조회수 기준 정렬)"""
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    search_response = (
        youtube.search()
        .list(
            q=keyword,
            part="id,snippet",
            type="video",
            order="viewCount",
            regionCode=region,
            publishedAfter=published_after,
            maxResults=max_results,
        )
        .execute()
    )

    video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
    if not video_ids:
        return []

    stats_response = (
        youtube.videos().list(part="statistics,snippet", id=",".join(video_ids)).execute()
    )

    results = []
    for item in stats_response.get("items", []):
        results.append(
            {
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "view_count": int(item["statistics"].get("viewCount", 0)),
                "like_count": int(item["statistics"].get("likeCount", 0)),
                "video_id": item["id"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
            }
        )

    results.sort(key=lambda x: x["view_count"], reverse=True)
    return results


def get_google_trends(keyword: str, region: str):
    """Google Trends 관심도 추이 + 연관 검색어"""
    try:
        pytrends = TrendReq(hl="ko-KR", tz=540)
        pytrends.build_payload([keyword], timeframe="today 3-m", geo=region)

        interest_over_time = pytrends.interest_over_time()
        related = pytrends.related_queries()

        trend_data = {
            "interest_trend": (
                interest_over_time[keyword].tolist() if not interest_over_time.empty else []
            ),
            "related_queries": {
                "top": related.get(keyword, {}).get("top").to_dict("records")
                if related.get(keyword, {}).get("top") is not None
                else [],
                "rising": related.get(keyword, {}).get("rising").to_dict("records")
                if related.get(keyword, {}).get("rising") is not None
                else [],
            },
        }
        return trend_data
    except Exception as e:
        print(f"[경고] Google Trends 조회 실패 (건너뜀): {e}")
        return {"interest_trend": [], "related_queries": {"top": [], "rising": []}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True, help="리서치할 키워드/주제")
    parser.add_argument("--region", default="KR", help="지역 코드 (기본값: KR)")
    parser.add_argument("--output", default="output/trends.json")
    args = parser.parse_args()

    if not YOUTUBE_API_KEY:
        raise SystemExit(".env 파일에 YOUTUBE_API_KEY를 설정하세요.")

    print(f"'{args.keyword}' 키워드로 YouTube 인기 영상 검색 중...")
    try:
        videos = search_youtube_videos(args.keyword, args.region)
    except HttpError as e:
        if e.resp.status == 403:
            raise SystemExit(
                "YouTube API 요청이 거부되었습니다 (403).\n"
                "일일 무료 할당량(10,000 유닛)을 다 썼거나 API 키가 잘못되었을 수 있습니다.\n"
                "할당량은 태평양시간 자정에 초기화됩니다."
            )
        raise

    print("Google Trends 관심도 조회 중...")
    trends = get_google_trends(args.keyword, args.region)

    result = {
        "keyword": args.keyword,
        "region": args.region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_videos": videos,
        "google_trends": trends,
    }

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {args.output}")
    print(f"상위 영상 {len(videos)}개 발견")
    if videos:
        print(f"1위: {videos[0]['title']} (조회수 {videos[0]['view_count']:,})")


if __name__ == "__main__":
    main()
