#!/usr/bin/env python3
"""Collect candidate Musinsa IPO/finance news for the briefing window. Standard library only.

This is a recall booster for runners with open network access (GitHub Actions, a local machine,
or a Claude Code cloud environment whose network policy allows these hosts). In a sandbox that
blocks them it exits with code 4 and the skill continues with the WebSearch tool alone.

Sources (each optional; a failing source never aborts the run):
  - Naver Search API (news)  needs NAVER_CLIENT_ID / NAVER_CLIENT_SECRET (free at developers.naver.com);
                             best Korean coverage and gives the publisher's original link
  - Google News RSS          no key; links are news.google.com redirects (find the original
                             article with WebSearch before citing it)

Usage:
  python3 collect_news.py --since-hours 24 --out out/candidates.json

Output: JSON {window, sources_ok, sources_failed, items:[{title, outlet, published_kst, url,
original_url, snippet, query, topic_hits, consumer_hits, consumer_suspect}]}, newest first.
Exit codes: 0 at least one source worked, 4 every source failed (likely blocked network).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; musinsa-ipo-daily-briefing/1.0)"

QUERIES = [
    "무신사 상장", "무신사 IPO", "무신사 공모", "무신사 예비심사", "무신사 증권신고서", "무신사 수요예측",
    "무신사 주관사", "무신사 기업가치", "무신사 장외", "무신사 비상장", "무신사 실적", "무신사 매출",
    "무신사 영업이익", "무신사 투자 유치", "무신사 지분", "무신사 감사보고서", "무신사 세무조사", "무신사 전망",
]
# Topic keywords that make an item relevant (at least one, plus '무신사', must appear).
TOPIC = [
    "상장", "IPO", "공모", "예비심사", "예심", "증권신고서", "수요예측", "청약", "주관사", "코스피", "유가증권",
    "실적", "매출", "영업이익", "영업손실", "순이익", "순손실", "적자", "흑자", "이익률", "거래액", "감사보고서",
    "회계", "재무", "기업가치", "밸류", "시가총액", "시총", "몸값", "장외", "비상장", "시세", "주가", "주식",
    "투자 유치", "투자유치", "시리즈", "프리IPO", "지분", "최대주주", "보호예수", "의무보유", "RSU", "스톡옵션",
    "우리사주", "세무조사", "추징", "전망", "분석", "동향", "리포트", "구조조정", "인수", "M&A", "자회사",
    "조만호", "CFO", "공정위", "과징금",
]
# Words that usually mean a shopping/consumer mention. They only flag an item for review.
CONSUMER = [
    "할인", "세일", "쿠폰", "특가", "블랙프라이데이", "무진장", "신상", "컬렉션", "룩북", "코디", "착용",
    "래플", "발매", "팝업", "입점", "단독 출시", "협업 출시", "이벤트", "증정", "랭킹", "추천템", "리뷰",
]


def fetch(url: str, headers: dict | None = None, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def naver(query: str) -> list[dict]:
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        raise RuntimeError("NAVER_CLIENT_ID/SECRET not set")
    url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode(
        {"query": query, "display": 100, "sort": "date"})
    data = json.loads(fetch(url, {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}))
    out = []
    for it in data.get("items", []):
        out.append({
            "title": clean(it.get("title")),
            "outlet": urllib.parse.urlparse(it.get("originallink") or it.get("link") or "").netloc,
            "published": parsedate_to_datetime(it["pubDate"]),
            "url": it.get("link") or it.get("originallink"),
            "original_url": it.get("originallink") or it.get("link"),
            "snippet": clean(it.get("description")),
        })
    return out


def google_news(query: str, days: int) -> list[dict]:
    q = f"{query} when:{max(1, days)}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    root = ET.fromstring(fetch(url))
    out = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        src = it.find("source")
        outlet = src.text.strip() if src is not None and src.text else ""
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3]
        out.append({
            "title": title,
            "outlet": outlet,
            "published": parsedate_to_datetime(it.findtext("pubDate")),
            "url": it.findtext("link"),
            "original_url": None,
            "snippet": clean(it.findtext("description"))[:300],
        })
    return out


def norm_key(title: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", title).lower()[:40]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since-hours", type=float, default=24)
    ap.add_argument("--out", default="out/candidates.json")
    args = ap.parse_args()

    now = dt.datetime.now(KST)
    since = now - dt.timedelta(hours=args.since_hours)
    days = int(args.since_hours // 24) + 1

    sources = {"naver": lambda q: naver(q), "google_news": lambda q: google_news(q, days)}
    ok, failed, raw = set(), {}, []
    for name, fn in sources.items():
        for q in QUERIES:
            try:
                for item in fn(q):
                    item["query"], item["via"] = q, name
                    raw.append(item)
                ok.add(name)
            except Exception as e:  # noqa: BLE001 - any failure just disables this source/query
                failed.setdefault(name, f"{type(e).__name__}: {e}"[:200])
                if name == "naver" and "not set" in str(e):
                    break  # no credentials: skip remaining Naver queries

    items, seen = [], set()
    for it in sorted(raw, key=lambda x: x["published"], reverse=True):
        pub = it["published"].astimezone(KST)
        if pub < since:
            continue
        text = f"{it['title']} {it['snippet']}"
        if "무신사" not in text:
            continue
        topic_hits = sorted({k for k in TOPIC if k.lower() in text.lower()})
        if not topic_hits:
            continue  # pure consumer/brand mention: never a briefing source
        key = norm_key(it["title"])
        if key in seen or it["url"] in seen:
            continue
        seen.update({key, it["url"]})
        consumer_hits = sorted({k for k in CONSUMER if k in text})
        items.append({
            "title": it["title"], "outlet": it["outlet"], "published_kst": pub.strftime("%Y-%m-%d %H:%M"),
            "url": it["url"], "original_url": it["original_url"], "snippet": it["snippet"],
            "query": it["query"], "via": it["via"], "topic_hits": topic_hits,
            "consumer_hits": consumer_hits, "consumer_suspect": len(consumer_hits) >= len(topic_hits),
        })

    result = {
        "window": {"since_kst": since.strftime("%Y-%m-%d %H:%M"), "until_kst": now.strftime("%Y-%m-%d %H:%M")},
        "sources_ok": sorted(ok),
        "sources_failed": {k: v for k, v in failed.items() if k not in ok},
        "count": len(items),
        "items": items,
    }
    summary = {k: result[k] for k in ("window", "sources_ok", "sources_failed", "count")}
    if not ok:
        # Write nothing: an empty candidates.json would look like real runner input on a re-run.
        print(json.dumps(summary | {"written": False}, ensure_ascii=False))
        return 4
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary | {"written": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
