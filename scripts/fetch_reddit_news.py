#!/usr/bin/env python3
"""
Fetch Reddit posts via JSON API with score filtering and noise reduction.

Replaces blogwatcher RSS for Reddit. Uses Reddit's public JSON API
(no authentication required). Outputs pipe-delimited TITLE|URL|SOURCE format.

Usage:
    python3 fetch_reddit_news.py [--hours 24] [--min-score 20]
"""

import json
import re
import ssl
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_SSL_CTX = ssl.create_default_context()

# ── Configuration ────────────────────────────────────────────────────
TIMEOUT = 20
MAX_WORKERS = 3
RETRY_COUNT = 1
RETRY_DELAY = 3
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Subreddit configs: dict with optional "flairs" list for flair filtering.
# When "flairs" is set, only posts matching those flairs are included
# (case-insensitive substring match on link_flair_text).
SUBREDDITS = [
    # Trading — primary focus
    {"sub": "wallstreetbets",       "sort": "hot", "limit": 50, "min_score": 500},
    {"sub": "options",              "sort": "hot", "limit": 25, "min_score": 100},
    {"sub": "thetagang",            "sort": "hot", "limit": 25, "min_score": 75},
    {"sub": "stocks",               "sort": "hot", "limit": 25, "min_score": 200},
    {"sub": "smallstreetbets",      "sort": "hot", "limit": 25, "min_score": 100},
    {"sub": "Daytrading",           "sort": "hot", "limit": 25, "min_score": 150},
    {"sub": "fatFIRE",              "sort": "hot", "limit": 25, "min_score": 100},

    # Crypto
    {"sub": "cryptocurrency",       "sort": "hot", "limit": 25, "min_score": 300},
    {"sub": "defi",                 "sort": "hot", "limit": 25, "min_score": 75},
    {"sub": "altcoin",              "sort": "hot", "limit": 25, "min_score": 50},

    # Legal tech
    {"sub": "legaltech",            "sort": "hot", "limit": 25, "min_score": 25},

    # Home Assistant
    {"sub": "homeassistant",        "sort": "hot", "limit": 25, "min_score": 100},
]

# Reddit noise filter — skip questions, rants, memes
NOISE_START = re.compile(
    r'^(Why|How|What|Can|Does|Is|Has|Are|Do|Should|Would|Could|Anyone|'
    r'Help|Rant|Vent|Am I|ELI5|CMV|PSA|Unpopular|Hot take|DAE|TIL|'
    r'Gah|Kindly explain|Seriously|From Frustration|Gemini Memory|'
    r'I just|I don.t|My experience|Thank you|Appreciation|Shoutout|'
    r'Just deleted|Thanks to everyone|I.m happy to report|'
    r'Overtaken!|F that|RIP|Goodbye)',
    re.IGNORECASE
)

# Relevance keywords (must match at least one)
SHORT_KW = re.compile(r'\b(SPY|QQQ|IWM|GLD|SLV|BTC|ETH|SOL|Fed|CPI|GDP|IPO|M&A|SEC|P&L)\b', re.IGNORECASE)
LONG_KW = re.compile(
    r'options|unusual activity|whale|dark pool|block trade|earnings|'
    r'bull call spread|put credit spread|iron condor|risk.reward|'
    r'support|resistance|breakout|catalyst|swing trade|'
    r'NVDA|TSLA|AAPL|AMZN|AMD|META|MSFT|GOOG|PLTR|SNAP|MSTR|COIN|'
    r'gold|silver|platinum|palladium|precious metal|GDX|GDXJ|'
    r'bitcoin|ethereum|solana|crypto|DeFi|memecoin|altcoin|'
    r'ONDO|INJ|FET|GRT|'
    r'Federal Reserve|rate decision|interest rate|inflation|tariff|sanctions|'
    r'geopolitical|OPEC|trade war|'
    r'legal tech|legal AI|court ruling|'
    r'Home Assistant|smart home|'
    r'acquisition|merger|funding|valuation|launch|release',
    re.IGNORECASE
)


def is_noise(title):
    """Return True if title looks like Reddit noise (questions, rants, etc)."""
    t = title.strip()
    if NOISE_START.match(t):
        return True
    if t.endswith('?'):
        return True
    if len(t) < 20:
        return True
    return False


def is_relevant(title):
    """Return True if title contains trading/crypto/metals/legal/HA keywords."""
    return bool(SHORT_KW.search(title) or LONG_KW.search(title))


def flair_matches(post_flair, allowed_flairs):
    """Check if a post's flair matches any in the allowed list (case-insensitive)."""
    if not post_flair:
        return False
    pf = post_flair.lower().strip()
    for af in allowed_flairs:
        if af.lower() in pf:
            return True
    return False


_JSON_BLOCKED = False  # Set True after first 403 to skip JSON for all subs


def fetch_subreddit(subreddit, sort, limit, min_score, cutoff, flairs=None):
    """Fetch posts from a single subreddit. If flairs is set, only matching posts."""
    global _JSON_BLOCKED

    # Skip JSON entirely if already blocked (avoid wasting requests)
    if _JSON_BLOCKED:
        return fetch_subreddit_rss(subreddit, sort, limit, cutoff, flairs)

    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&raw_json=1"

    for attempt in range(RETRY_COUNT + 1):
        try:
            req = Request(url, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'text/html,application/json',
            })
            with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            posts = []
            for child in data.get('data', {}).get('children', []):
                post = child.get('data', {})
                if not post:
                    continue

                created_utc = post.get('created_utc', 0)
                post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if post_time < cutoff:
                    continue

                score = post.get('score', 0)
                if score < min_score:
                    continue

                if post.get('stickied', False):
                    continue

                title = post.get('title', '').strip()
                if not title:
                    continue

                if flairs:
                    post_flair = post.get('link_flair_text', '')
                    if not flair_matches(post_flair, flairs):
                        continue

                if is_noise(title):
                    continue

                on_topic = subreddit.lower() in {
                    'wallstreetbets', 'options', 'thetagang', 'stocks',
                    'smallstreetbets', 'daytrading', 'fatfire',
                    'cryptocurrency', 'defi', 'altcoin',
                    'legaltech', 'homeassistant',
                }
                if not on_topic and not is_relevant(title):
                    continue

                permalink = f"https://www.reddit.com{post.get('permalink', '')}"
                external_url = post.get('url', '')
                is_self = post.get('is_self', True)

                if is_self or 'reddit.com' in external_url or 'redd.it' in external_url:
                    link = permalink
                else:
                    link = external_url

                title_clean = title.replace('|', ' -')
                num_comments = post.get('num_comments', 0)

                posts.append({
                    'title': title_clean,
                    'url': link,
                    'source': f"r/{subreddit}",
                    'score': score,
                    'comments': num_comments,
                })

            return posts

        except HTTPError as e:
            if e.code == 429 and attempt < RETRY_COUNT:
                time.sleep(10)
                continue
            elif e.code == 403:
                # JSON API blocked — fall back to RSS for this and all future subs
                _JSON_BLOCKED = True
                return fetch_subreddit_rss(subreddit, sort, limit, cutoff, flairs)
            print(f"  Warning: r/{subreddit}: HTTP {e.code}", file=sys.stderr)
        except (URLError, OSError) as e:
            print(f"  Warning: r/{subreddit}: network error", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: r/{subreddit}: {e}", file=sys.stderr)

        if attempt < RETRY_COUNT:
            time.sleep(RETRY_DELAY)

    return []


def fetch_subreddit_rss(subreddit, sort, limit, cutoff, flairs=None):
    """Fallback: fetch posts via Reddit RSS (Atom) when JSON API returns 403."""
    import xml.etree.ElementTree as ET

    # Delay between RSS requests to avoid rate limiting
    time.sleep(2)

    url = f"https://www.reddit.com/r/{subreddit}/{sort}.rss?limit={limit}"

    try:
        req = Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,*/*',
        })
        with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
            content = resp.read().decode('utf-8')

        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        root = ET.fromstring(content)
        entries = root.findall('atom:entry', ns)

        posts = []
        on_topic = subreddit.lower() in {
            'wallstreetbets', 'options', 'thetagang', 'stocks',
            'smallstreetbets', 'daytrading', 'fatfire',
            'cryptocurrency', 'defi', 'altcoin',
            'legaltech', 'homeassistant',
        }

        for entry in entries:
            title_el = entry.find('atom:title', ns)
            link_el = entry.find('atom:link', ns)
            updated_el = entry.find('atom:updated', ns)

            if title_el is None or link_el is None:
                continue

            title = title_el.text.strip() if title_el.text else ''
            link = link_el.get('href', '')

            if not title or not link:
                continue
            if is_noise(title):
                continue
            if not on_topic and not is_relevant(title):
                continue

            title_clean = title.replace('|', ' -')
            posts.append({
                'title': title_clean,
                'url': link,
                'source': f"r/{subreddit}",
                'score': 0,
                'comments': 0,
            })

        if posts:
            print(f"  r/{subreddit}: {len(posts)} posts via RSS fallback", file=sys.stderr)
        return posts

    except Exception as e:
        print(f"  Warning: r/{subreddit} RSS fallback failed: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="Fetch Reddit posts via JSON API")
    parser.add_argument('--hours', type=int, default=24, help='Hours lookback (default: 24)')
    parser.add_argument('--min-score', type=int, default=0, help='Override min score for all subs')
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    all_posts = []
    # Use 1 worker when RSS fallback is active (rate limit sensitive)
    workers = 1 if _JSON_BLOCKED else MAX_WORKERS
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for cfg in SUBREDDITS:
            sub = cfg["sub"]
            sort = cfg.get("sort", "hot")
            limit = cfg.get("limit", 25)
            min_score = cfg.get("min_score", 30)
            flairs = cfg.get("flairs", None)
            effective_min = args.min_score if args.min_score > 0 else min_score
            future = pool.submit(fetch_subreddit, sub, sort, limit, effective_min, cutoff, flairs)
            futures[future] = sub

        for future in as_completed(futures):
            posts = future.result()
            all_posts.extend(posts)

    all_posts.sort(key=lambda x: -x['score'])

    seen_urls = set()
    unique_posts = []
    for post in all_posts:
        if post['url'] not in seen_urls:
            seen_urls.add(post['url'])
            unique_posts.append(post)

    for post in unique_posts:
        print(f"{post['title']}|{post['url']}|{post['source']}")

    print(f"  Done: {len(unique_posts)} posts from {len(SUBREDDITS)} subreddits", file=sys.stderr)


if __name__ == "__main__":
    main()
