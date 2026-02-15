import os
import requests
import snscrape.modules.twitter as sntwitter


def fetch_latest_tweets(username: str, limit: int = 20) -> list[dict]:
    """
    Fetch latest tweets from a user using snscrape.
    Returns a list of dicts that match Apps Script webhook schema:
      tweet_id, tweet_url, author, created_at, text, raw
    """
    u = username.strip().lstrip("@")
    scraper = sntwitter.TwitterUserScraper(u)

    items: list[dict] = []
    for i, tweet in enumerate(scraper.get_items()):
        if i >= limit:
            break

        tweet_id = str(tweet.id)
        tweet_url = f"https://x.com/{u}/status/{tweet_id}"

        try:
            created_at = tweet.date.isoformat()
        except Exception:
            created_at = ""

        # snscrape 최신 객체는 rawContent를 주로 씀
        text = getattr(tweet, "rawContent", None) or getattr(tweet, "content", "") or ""

        items.append({
            "tweet_id": tweet_id,
            "tweet_url": tweet_url,
            "author": u,
            "created_at": created_at,
            "text": text,
            "raw": {
                "likeCount": getattr(tweet, "likeCount", None),
                "retweetCount": getattr(tweet, "retweetCount", None),
                "replyCount": getattr(tweet, "replyCount", None),
                "quoteCount": getattr(tweet, "quoteCount", None),
                "lang": getattr(tweet, "lang", None),
            },
        })

    return items


def post_to_webhook(webhook_url: str, token: str, items: list[dict]) -> str:
    payload = {"token": token, "items": items}
    r = requests.post(webhook_url, json=payload, timeout=45)
    r.raise_for_status()
    return r.text


def main():
    username = os.environ["X_USERNAME"].strip()
    print("DEBUG username repr:", repr(username))
    webhook_url = os.environ["SHEETS_WEBHOOK_URL"].strip()
    token = os.environ["SHEETS_WEBHOOK_TOKEN"].strip()

    tweets = fetch_latest_tweets(username, limit=20)

    # 수집이 0개여도 웹훅 호출은 할 수 있지만, 불필요하면 건너뛰게 처리
    if not tweets:
        print("OK (no tweets fetched)")
        print("sent_items: 0")
        return

    resp = post_to_webhook(webhook_url, token, tweets)

    print("OK")
    print("sent_items:", len(tweets))
    print("webhook_resp:", resp)


if __name__ == "__main__":
    main()
