import json
import os
import sqlite3
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env from project root if present (so SCRAPFLY_KEY / SCRAPFLY_USE_TEST / SCRAPFLY_TEST_KEY work)
_project_root = Path(__file__).resolve().parent.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k:
                os.environ.setdefault(k, v)

# Add the scrapfly-scrapers directory to the path to import the twitter scraper
SCRAPER_PATH = _project_root / "scrapfly-scrapers" / "twitter-scraper"
sys.path.insert(0, str(SCRAPER_PATH))

import jmespath
from scrapfly import ScrapeConfig, ScrapflyClient

DB_PATH = _project_root / "icenews_social.db"

ALLOWED_CATEGORIES = {"government", "independent", "unknown"}

# How many newest posts to ingest per account per run.
# This is the key knob for “10 posts a day”: run this once daily and keep this at 10.
MAX_TWEETS_PER_ACCOUNT = int(os.environ.get("ICENEWS_MAX_TWEETS_PER_ACCOUNT", "10"))

# Initialize Scrapfly client (use test key when SCRAPFLY_USE_TEST=1)
_use_test = os.environ.get("SCRAPFLY_USE_TEST", "").strip() == "1"
SCRAPFLY_KEY = os.environ.get("SCRAPFLY_TEST_KEY") if _use_test else os.environ.get("SCRAPFLY_KEY")
if not SCRAPFLY_KEY:
    raise ValueError(
        "Set SCRAPFLY_KEY (live) or SCRAPFLY_USE_TEST=1 with SCRAPFLY_TEST_KEY in environment"
    )
SCRAPFLY = ScrapflyClient(key=SCRAPFLY_KEY)
BASE_CONFIG = {
    "asp": True,  # Anti Scraping Protection bypass
    "render_js": True,  # JavaScript rendering required
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_enabled_accounts(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT account_id, platform, handle, display_name, category
        FROM accounts
        WHERE is_enabled = 1 AND platform = 'x'
    """)
    return cur.fetchall()

def insert_post(conn, post: dict) -> bool:
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO posts (
            platform, post_id, url, tagged_account_handle, tagged_hashtags, language,
            author_handle, author_display_name,
            category, text, created_at, retrieved_at,
            media_json, metrics_json,
            raw_json, account_id,
            reply_to_post_id, quoted_post_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post["platform"],
        post["post_id"],
        post["url"],
        post.get("tagged_account_handle"),
        post.get("tagged_hashtags"),
        post.get("language"),
        post.get("author_handle"),
        post.get("author_display_name"),
        post["category"],
        post.get("text"),
        post.get("created_at"),
        post.get("retrieved_at"),
        json.dumps(post.get("media", []), ensure_ascii=False),
        json.dumps(post.get("metrics", {}), ensure_ascii=False),
        json.dumps(post.get("raw_json", {}), ensure_ascii=False),
        post.get("account_id"),
        post.get("reply_to_post_id"),
        post.get("quoted_post_id"),
    ))
    return cur.rowcount == 1

def parse_tweet_from_data(data: dict) -> dict:
    """Parse a tweet from Twitter API response data using jmespath"""
    result = jmespath.search(
        """{
        created_at: legacy.created_at,
        attached_urls: legacy.entities.urls[].expanded_url,
        attached_urls2: legacy.entities.url.urls[].expanded_url,
        attached_media: legacy.entities.media[].media_url_https,
        tagged_users: legacy.entities.user_mentions[].screen_name,
        tagged_hashtags: legacy.entities.hashtags[].text,
        favorite_count: legacy.favorite_count,
        bookmark_count: legacy.bookmark_count,
        quote_count: legacy.quote_count,
        reply_count: legacy.reply_count,
        retweet_count: legacy.retweet_count,
        text: legacy.full_text,
        is_quote: legacy.is_quote_status,
        is_retweet: legacy.retweeted,
        language: legacy.lang,
        user_id: legacy.user_id_str,
        id: legacy.id_str,
        conversation_id: legacy.conversation_id_str,
        source: source,
        views: views.count,
        in_reply_to_status_id: legacy.in_reply_to_status_id_str,
        quoted_status_id: legacy.quoted_status_id_str
    }""",
        data,
    )
    return result or {}

async def scrape_profile_with_tweets(handle: str) -> list:
    """
    Scrape a Twitter profile and extract tweets from the profile page.
    Returns a list of tweet dictionaries.
    """
    url = f"https://x.com/{handle}"
    
    # Scrape the profile page with retry logic
    _retries = 0
    while True:
        try:
            result = await SCRAPFLY.async_scrape(
                ScrapeConfig(url, auto_scroll=True, lang=["en-US"], wait_for_selector="xhr:UserTweets", **BASE_CONFIG)
            )
            
            if "Something went wrong, but" in result.content:
                if _retries > 2:
                    raise Exception(f"Twitter web app crashed too many times for {handle}")
                _retries += 1
                continue
            break
        except Exception as e:
            if _retries > 2:
                raise
            _retries += 1
    
    # Extract tweets from xhr calls
    tweets = []
    _xhr_calls = result.scrape_result["browser_data"]["xhr_call"]
    
    # Look for UserTweets API calls
    tweet_calls = [f for f in _xhr_calls if "UserTweets" in f["url"]]
    
    for xhr in tweet_calls:
        if not xhr.get("response"):
            continue
        try:
            data = json.loads(xhr["response"]["body"])
            # Extract tweets from the response structure
            # The structure may vary, so we try multiple paths
            entries = (
                jmespath.search("data.user.result.timeline_v2.timeline.instructions[*].entries[]", data) or
                jmespath.search("data.user.result.timeline.timeline.instructions[*].entries[]", data) or
                []
            )
            
            for entry in entries:
                # Extract tweet data from entry
                tweet_data = jmespath.search("content.itemContent.tweet_results.result", entry)
                if tweet_data:
                    parsed_tweet = parse_tweet_from_data(tweet_data)
                    if parsed_tweet.get("id"):
                        # Build tweet URL
                        parsed_tweet["url"] = f"https://x.com/{handle}/status/{parsed_tweet['id']}"
                        tweets.append(parsed_tweet)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            continue
    
    return tweets

def normalize_scraper_item(item: dict, account_row: dict) -> dict:
    """
    Map the maintained scraper’s tweet object -> your DB schema.
    You will adjust the field names here after you inspect one real output sample.
    """
    platform = "x"
    category = account_row["category"] if account_row["category"] in ALLOWED_CATEGORIES else "unknown"

    # Extract fields from the parsed tweet structure
    post_id = str(item.get("id") or "")
    text = item.get("text") or ""
    created_at = item.get("created_at") or None
    
    # Build URL if not present
    url = item.get("url") or ""
    if not url and post_id:
        url = f"https://x.com/{account_row['handle']}/status/{post_id}"

    if not post_id:
        return None

    # Extract media URLs
    media = []
    attached_media = item.get("attached_media") or []
    if attached_media:
        media = [{"url": url, "type": "photo"} for url in attached_media]
    
    # Build metrics dictionary
    metrics = {
        "favorite_count": item.get("favorite_count", 0),
        "retweet_count": item.get("retweet_count", 0),
        "reply_count": item.get("reply_count", 0),
        "quote_count": item.get("quote_count", 0),
        "bookmark_count": item.get("bookmark_count", 0),
        "views": item.get("views", 0),
    }
    
    # Extract tagged_users and tagged_hashtags
    tagged_users = item.get("tagged_users") or []
    tagged_hashtags = item.get("tagged_hashtags") or []
    # Convert arrays to JSON strings for storage
    tagged_account_handle = json.dumps(tagged_users, ensure_ascii=False) if tagged_users else None
    tagged_hashtags_json = json.dumps(tagged_hashtags, ensure_ascii=False) if tagged_hashtags else None

    return {
        "platform": platform,
        "post_id": post_id,
        "url": url,
        "tagged_account_handle": tagged_account_handle,
        "tagged_hashtags": tagged_hashtags_json,
        "language": item.get("language"),
        "account_id": account_row["id"],
        "author_handle": account_row["handle"],
        "author_display_name": account_row["display_name"],
        "category": category,
        "text": text,
        "created_at": created_at,
        "retrieved_at": now_iso(),
        "media": media,
        "metrics": metrics,
        "reply_to_post_id": item.get("in_reply_to_status_id"),
        "quoted_post_id": item.get("quoted_status_id"),
        "raw_json": item,
    }

async def process_account(conn, account_row: dict) -> int:
    """Process a single account: scrape tweets and insert into database"""
    handle = account_row["handle"]
    
    try:
        # Scrape profile and get tweets
        tweets = await scrape_profile_with_tweets(handle)

        # Defense-in-depth:
        # - Deduplicate by tweet id
        # - Keep only the newest N to cap cost/work per run
        #
        # Professor-tip: if you later want “exactly 10 new posts/day”, you’ll
        # need a concept of “last seen” (cursor) per account. For now we rely on
        # INSERT OR IGNORE plus “fetch latest N” which is simple and robust.
        seen = set()
        deduped = []
        for t in tweets:
            tid = t.get("id")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            deduped.append(t)
        tweets = deduped[:max(1, MAX_TWEETS_PER_ACCOUNT)]
        
        if not tweets:
            print(f"[{handle}] no tweets found")
            return 0
        
        inserted = 0
        for tweet in tweets:
            norm = normalize_scraper_item(tweet, account_row)
            if not norm:
                continue
            if insert_post(conn, norm):
                inserted += 1
        
        conn.commit()
        print(f"[{handle}] inserted {inserted}/{len(tweets)}")
        return inserted
        
    except Exception as e:
        print(f"[{handle}] scraper failed: {str(e)[:300]}")
        conn.rollback()
        return 0

async def run_async():
    """Async version of run() that uses direct Scrapfly integration"""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    accounts = get_enabled_accounts(conn)
    print(f"Enabled X accounts: {len(accounts)}")

    total_inserted = 0

    # Process accounts sequentially to avoid overwhelming the API
    for (acc_id, platform, handle, display_name, category) in accounts:
        account_row = {
            "id": acc_id,
            "handle": handle,
            "display_name": display_name,
            "category": category,
        }
        
        inserted = await process_account(conn, account_row)
        total_inserted += inserted

    conn.close()
    print(f"Done. Total inserted: {total_inserted}")

def run():
    """Synchronous entry point that runs the async function"""
    asyncio.run(run_async())

if __name__ == "__main__":
    run()
