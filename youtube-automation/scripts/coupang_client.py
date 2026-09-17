"""
쿠팡 파트너스 Open API 클라이언트

상품 정보와 이미지, 그리고 수수료가 붙는 구매 링크(딥링크)를 받아옵니다.

인증은 HMAC-SHA256입니다. 서명할 문자열은 "시각 + HTTP메서드 + 경로 + 쿼리"이고,
시각은 UTC를 yyMMddTHHmmssZ 형식으로 씁니다. 컴퓨터 시계가 서버와 몇 분 이상
어긋나면 401이 납니다.

주의: 서명에 쓴 쿼리 문자열과 실제로 보내는 쿼리가 글자 하나까지 같아야 합니다.
한글 키워드는 여기서 한 번만 인코딩하고, 그 결과를 서명과 요청에 똑같이 씁니다.

키 발급: 쿠팡 파트너스(partners.coupang.com) 가입 후 승인되면
"내 정보 → 오픈 API 키 발급"에서 받습니다.
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

DOMAIN = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1"

# 카테고리 ID. "신기한 물건"이 잘 나오는 쪽을 기본으로 씁니다.
CATEGORIES = {
    "여성패션": 1001, "남성패션": 1002, "뷰티": 1010, "출산유아동": 1011,
    "식품": 1012, "주방용품": 1013, "생활용품": 1014, "홈인테리어": 1015,
    "가전디지털": 1016, "스포츠레저": 1017, "자동차용품": 1018, "도서음반DVD": 1019,
    "완구취미": 1020, "문구오피스": 1021, "헬스건강식품": 1024,
    "반려동물용품": 1029, "유아동패션": 1030,
}


class CoupangError(RuntimeError):
    pass


class CoupangPartners:
    def __init__(self, access_key=None, secret_key=None, timeout=15.0):
        self.access_key = access_key or os.getenv("COUPANG_ACCESS_KEY", "")
        self.secret_key = secret_key or os.getenv("COUPANG_SECRET_KEY", "")
        self.timeout = timeout
        if not self.access_key or not self.secret_key:
            raise CoupangError(
                ".env에 COUPANG_ACCESS_KEY와 COUPANG_SECRET_KEY를 넣어주세요.\n"
                "쿠팡 파트너스(partners.coupang.com)에 가입해 승인받은 뒤\n"
                "'내 정보 → 오픈 API 키 발급'에서 받을 수 있습니다."
            )

    def _auth_header(self, method: str, path: str, query: str) -> str:
        signed_date = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        message = signed_date + method + path + query
        signature = hmac.new(
            self.secret_key.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return (
            f"CEA algorithm=HmacSHA256, access-key={self.access_key}, "
            f"signed-date={signed_date}, signature={signature}"
        )

    def _request(self, method: str, path: str, params=None, body=None):
        full_path = BASE + path
        # quote_via=quote를 써야 공백이 +가 아니라 %20이 됩니다. 서명과 요청이
        # 한 글자라도 다르면 401 Invalid signature가 납니다.
        query = urlencode(
            {k: v for k, v in (params or {}).items() if v is not None}, quote_via=quote
        )
        url = DOMAIN + full_path + (f"?{query}" if query else "")

        headers = {
            "Authorization": self._auth_header(method, full_path, query),
            "Content-Type": "application/json",
        }

        try:
            resp = requests.request(
                method, url, headers=headers,
                data=json.dumps(body) if body is not None else None,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise CoupangError(f"쿠팡 API 연결 실패: {e}")

        if resp.status_code == 401:
            raise CoupangError(
                "쿠팡 API 인증 실패(401)입니다.\n"
                "키가 맞는지, 그리고 컴퓨터 시계가 정확한지 확인하세요.\n"
                "시계가 몇 분만 어긋나도 인증이 거부됩니다."
            )
        if resp.status_code != 200:
            raise CoupangError(f"쿠팡 API 오류 HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        if str(data.get("rCode")) != "0":
            raise CoupangError(f"쿠팡 API 오류 rCode={data.get('rCode')} {data.get('rMessage')}")
        return data.get("data")

    def goldbox(self, sub_id=None) -> list:
        """오늘의 골드박스 — 할인 특가라 '싸다'는 훅이 잘 먹힙니다"""
        return self._request("GET", "/products/goldbox", {"subId": sub_id}) or []

    def best_category(self, category_id: int, limit: int = 30, sub_id=None) -> list:
        """카테고리별 인기 상품"""
        return self._request(
            "GET", f"/products/bestcategories/{category_id}",
            {"limit": limit, "subId": sub_id},
        ) or []

    def search(self, keyword: str, limit: int = 20, sub_id=None) -> list:
        data = self._request(
            "GET", "/products/search", {"keyword": keyword, "limit": limit, "subId": sub_id}
        )
        if isinstance(data, dict):
            return data.get("productData", []) or []
        return data or []

    def deeplink(self, urls: list, sub_id=None) -> list:
        """일반 쿠팡 주소를 수수료가 붙는 파트너스 링크로 바꿉니다"""
        body = {"coupangUrls": urls}
        if sub_id:
            body["subId"] = sub_id
        return self._request("POST", "/deeplink", body=body) or []


def normalize(item: dict) -> dict:
    """API 응답에서 필요한 것만 추려 쓰기 좋은 모양으로 바꾼다"""
    return {
        "id": str(item.get("productId", "")),
        "name": str(item.get("productName", "")).strip(),
        "price": int(float(item.get("productPrice") or 0)),
        "image": item.get("productImage") or "",
        "url": item.get("productUrl") or "",
        "rocket": bool(item.get("isRocket")),
        "free_shipping": bool(item.get("isFreeShipping")),
        "category": item.get("categoryName") or "",
    }


if __name__ == "__main__":
    # 키가 제대로 동작하는지 확인하는 용도
    import sys

    try:
        client = CoupangPartners()
        items = client.goldbox()
    except CoupangError as e:
        sys.exit(str(e))

    print(f"골드박스 상품 {len(items)}개를 받았습니다.")
    for item in items[:5]:
        p = normalize(item)
        print(f"  {p['price']:>8,}원  {p['name'][:45]}")
