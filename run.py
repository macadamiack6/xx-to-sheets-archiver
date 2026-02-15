import os
import time
import json
import hashlib
from datetime import datetime, timezone

import feedparser
import requests


# 여러 Nitter 인스턴스를 순서대로 시도 (죽은 인스턴스 대비)
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.lacontrevoie.fr",
]

def build_feed_urls(username: str) -> list[str]:
    username = username.strip().lstrip("@")
    return [f"{base}/{username}/rss" for base in NITTER_INSTANCES]

def pick_entries(feed, username: str) -> list[dict]:
    items = pick_entries(feed, username)
    for e in getattr(feed, "entries", []) or []:
        # Nitter RSS에서 보통 link가 트윗 URL(또는 프록시 URL)로 들어옴
        link = (e.get("link") or "").strip()
        title = (e.get("title") or "").strip()
        published = (e.get("published") or e.get("updated") or "").strip()
        author = (e.get("author") or "").strip()

        # tweet_id는 확실하지 않아서 link 기반 해시로 대체 (시트 중복방지용)
        # (가능하면 나중에 파싱 로직 개선 가능)
        tweet_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:20] if link else ""
        items.append({
            "tweet_id": tweet_id,
            "tweet_url": link,
            "author": author or username,
            "created_at": published,
            "text": title,
        })
    return items

def fetch_feed(username: str):
    last_err = None
    for url in build_feed_urls(username):
        try:
            # feedparser가 내부에서 requests를 쓰진 않아서, 직접 가져와서 파싱 (타임아웃/헤더 제어)
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (RSS archiver)"})
            if r.status_code != 200:
                last_err = f"{url} -> HTTP {r.status_code}"
                continue
            feed = feedparser.parse(r.text)
            if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
                last_err = f"{url} -> parse error"
                continue
            return url, feed
        except Exception as e:
            last_err = f"{url} -> {e}"
    raise RuntimeError(f"All Nitter feeds failed. Last error: {last_err}")

def post_to_webhook(webhook_url: str, token: str, items: list[dict]):
    payload = {"token": token, "items": items}
    r = requests.post(webhook_url, json=payload, timeout=30)
    r.raise_for_status()
    return r.text

def main():
    username = os.environ["X_USERNAME"]
    webhook_url = os.environ["SHEETS_WEBHOOK_URL"]
    token = os.environ["SHEETS_WEBHOOK_TOKEN"]

    source_url, feed = fetch_feed(username)
    items = pick_entries(feed)

    # 최신 N개만 전송 (너무 많이 보내면 시트/실행 시간 부담)
    items = items[:20]

    resp = post_to_webhook(webhook_url, token, items)

    print("OK")
    print("source:", source_url)
    print("sent_items:", len(items))
    print("webhook_resp:", resp)

if __name__ == "__main__":
    main()
