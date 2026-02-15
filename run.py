import os
import time
import hashlib
import random
import feedparser
import requests

# Nitter 인스턴스 (일부는 수시로 죽어서 "많이" 넣는 게 핵심)
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.blahaj.land",
    "https://nitter.bird.froth.zone",
    "https://nitter.buntcomm.com",
    "https://nitter.cabletemple.net",
    "https://nitter.colibriste.org",
    "https://nitter.crabf.art",
    "https://nitter.eda.gay",
    "https://nitter.fullex.fr",
    "https://nitter.gorb.lol",
    "https://nitter.grimneko.de",
    "https://nitter.jejik.nl",
    "https://nitter.kavin.rocks",
    "https://nitter.lunar.icu",
    "https://nitter.mint.lgbt",
    "https://nitter.moomoo.me",
    "https://nitter.schleuss.online",
    "https://nitter.tiekoetter.com",
    "https://nitter.wisq.net",
]

# xcancel RSS도 같이 시도 (작동/차단 케이스가 있어서 "옵션"으로 넣음)
# 어떤 환경에선 특정 User-Agent가 필요하다는 보고가 있음 :contentReference[oaicite:1]{index=1}
XCANCEL_FEEDS = [
    "https://rss.xcancel.com/{u}/rss",
    "https://xcancel.com/{u}/rss",
]

def build_feed_urls(username: str) -> list[str]:
    u = username.strip().lstrip("@")

    urls = [tmpl.format(u=u) for tmpl in XCANCEL_FEEDS]
    urls += [f"{base}/{u}/rss" for base in NITTER_INSTANCES]

    # 항상 같은 순서로만 두드리면 특정 인스턴스만 망가질 수 있어서 셔플
    random.shuffle(urls)
    return urls

def pick_entries(feed, username: str) -> list[dict]:
    items = []
    for e in getattr(feed, "entries", []) or []:
        link = (e.get("link") or "").strip()
        title = (e.get("title") or "").strip()
        published = (e.get("published") or e.get("updated") or "").strip()
        author = (e.get("author") or "").strip()

        # tweet_id는 RSS에서 안정적으로 못 얻는 경우가 있어 link 해시로 중복 방지
        tweet_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:20] if link else ""

        items.append({
            "tweet_id": tweet_id,
            "tweet_url": link,
            "author": author or username,
            "created_at": published,
            "text": title,
        })
    return items

def http_get_with_retry(url: str, timeout: int = 25) -> requests.Response:
    # xcancel에서 UA 요구 케이스가 있어서 둘 다 시도
    user_agents = [
        "Mozilla/5.0 (RSS archiver)",
        "mistique",  # xcancel 관련 이슈에서 언급됨 :contentReference[oaicite:2]{index=2}
    ]

    last_err = None
    for attempt in range(1, 4):  # 최대 3회
        for ua in user_agents:
            try:
                r = requests.get(url, timeout=timeout, headers={"User-Agent": ua})
                # 503/429는 잠깐 쉬고 재시도 가치가 큼
                if r.status_code in (429, 503):
                    last_err = f"HTTP {r.status_code}"
                    continue
                return r
            except Exception as e:
                last_err = str(e)

        # 백오프 (1s, 2s, 4s)
        time.sleep(2 ** (attempt - 1))

    raise RuntimeError(last_err or "request failed")

def fetch_feed(username: str):
    last_err = None
    urls = build_feed_urls(username)

    for url in urls:
        try:
            r = http_get_with_retry(url)
            if r.status_code != 200:
                last_err = f"{url} -> HTTP {r.status_code}"
                continue

            feed = feedparser.parse(r.text)
            if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
                last_err = f"{url} -> parse error"
                continue

            # entries가 비어있으면 다음 후보로
            if not getattr(feed, "entries", None):
                last_err = f"{url} -> empty feed"
                continue

            return url, feed

        except Exception as e:
            last_err = f"{url} -> {e}"

    raise RuntimeError(f"All feeds failed. Last error: {last_err}")

def post_to_webhook(webhook_url: str, token: str, items: list[dict]):
    payload = {"token": token, "items": items}
    r = requests.post(webhook_url, json=payload, timeout=30)
    r.raise_for_status()
    return r.text

def main():
    username = os.environ["X_USERNAME"].strip().lstrip("@")
    webhook_url = os.environ["SHEETS_WEBHOOK_URL"].strip()
    token = os.environ["SHEETS_WEBHOOK_TOKEN"].strip()

    source_url, feed = fetch_feed(username)
    items = pick_entries(feed, username)

    # 최신 N개만
    items = items[:20]

    resp = post_to_webhook(webhook_url, token, items)

    print("OK")
    print("source:", source_url)
    print("sent_items:", len(items))
    print("webhook_resp:", resp)

if __name__ == "__main__":
    main()
