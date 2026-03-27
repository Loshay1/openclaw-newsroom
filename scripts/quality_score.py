#!/usr/bin/env python3
"""
Quality scoring pre-filter for the news scan pipeline.

Reads pipe-delimited articles (TITLE|URL|SOURCE or TITLE|URL|SOURCE|TIER),
scores them based on source tier, title quality, freshness signals, and
deduplicates by title similarity.

Outputs the top N articles in the same pipe-delimited format, sorted by score.

Usage:
    python3 quality_score.py --input articles.txt [--max 50] [--dedup-threshold 0.80]
"""

import sys
import re
import argparse
from difflib import SequenceMatcher

try:
    from dedup_db import DedupDB, normalize_url
    HAS_DEDUP_DB = True
except ImportError:
    HAS_DEDUP_DB = False

# ── Source priority scoring ──────────────────────────────────────────
# Higher = better. Customize to match your blogwatcher feed names.
PRIORITY_SOURCES = {
    # T1: Wire services + flow data + metals (+5 bonus)
    'Bloomberg Markets': 5, 'Reuters Business': 5, 'Federal Reserve': 5,
    'Unusual Whales Flow': 5, 'CoinDesk': 5, 'Kitco News': 5,
    'Home Assistant Blog': 5, 'Artificial Lawyer': 5,
    # T2: Financial press + legal + crypto (+3 bonus)
    'CNBC Options Action': 3, 'MarketWatch Top Stories': 3,
    'Seeking Alpha Market News': 3, 'The Block': 3,
    'Above the Law': 3, 'AP News World': 3, 'Law.com Legal Tech': 3,
    'ABA Journal Tech': 3, 'Gold.org (World Gold Council)': 3, 'Decrypt': 3,
    # T3: Aggregators / community (+1 bonus)
    'Zero Hedge': 1,
    # X/Twitter (+2 — original source, not aggregated)
    'X/Twitter': 2,
}

# High-value keywords that boost score (+50 points class)
HIGH_VALUE_KEYWORDS = re.compile(
    r'\b(unusual options activity|whale|dark pool|block trade|'
    r'earnings surprise|Fed rate|gold breakout|silver squeeze|'
    r'BTC breakout|ETH ETF|acquisition|merger|billion)\b',
    re.IGNORECASE
)

# Medium-value keywords (+25 points class)
MEDIUM_VALUE_KEYWORDS = re.compile(
    r'\b(bull call spread|put credit spread|iron condor|risk.reward|'
    r'support.resistance|catalyst|DeFi|memecoin|legal AI|'
    r'Home Assistant|swing trade|technical analysis|macro|tariff|sanctions)\b',
    re.IGNORECASE
)

# Signal words for breaking/exclusive news
BREAKING_KEYWORDS = re.compile(
    r'\b(breaking|exclusive|just in|confirmed|leaked|first look|'
    r'officially|unveil|reveal|flash crash|circuit breaker|halt)\b',
    re.IGNORECASE
)

# Auto-kill keywords (-999)
KILL_KEYWORDS = re.compile(
    r'\b(paid course|join my discord|not financial advice|'
    r'penny stock|guaranteed returns)\b',
    re.IGNORECASE
)

# Soft penalty keywords (-25)
PENALTY_KEYWORDS = re.compile(
    r'\b(top 10|listicle|sponsored)\b',
    re.IGNORECASE
)


def title_similarity(t1, t2):
    """Fast title similarity using SequenceMatcher."""
    return SequenceMatcher(None, t1.lower(), t2.lower()).ratio()


def compute_score(title, source, tier_str):
    """Compute a quality score for an article."""
    score = 0

    score += PRIORITY_SOURCES.get(source, 0)

    if source.startswith('r/'):
        score += 1

    if source.startswith('GitHub'):
        score += 2

    try:
        tier = int(tier_str) if tier_str else 3
    except ValueError:
        tier = 3
    if tier == 1:
        score += 4
    elif tier == 2:
        score += 2
    elif tier == 3:
        score += 1

    # Kill keywords — auto-reject
    if KILL_KEYWORDS.search(title):
        return -999

    # Soft penalty
    if PENALTY_KEYWORDS.search(title):
        score -= 25

    # High-value keywords (+50 each, capped at 100)
    hv_matches = HIGH_VALUE_KEYWORDS.findall(title)
    score += min(len(hv_matches) * 50, 100)

    # Medium-value keywords (+25 each, capped at 50)
    mv_matches = MEDIUM_VALUE_KEYWORDS.findall(title)
    score += min(len(mv_matches) * 25, 50)

    if BREAKING_KEYWORDS.search(title):
        score += 30

    title_len = len(title)
    if title_len < 30:
        score -= 1
    elif 50 <= title_len <= 150:
        score += 1

    return score


def deduplicate(articles, threshold=0.80):
    """Remove near-duplicate articles by title similarity. Keep highest-scored."""
    unique = []
    for article in articles:
        is_dup = False
        for existing in unique:
            sim = title_similarity(article['title'], existing['title'])
            if sim >= threshold:
                is_dup = True
                if article['score'] > existing['score']:
                    unique.remove(existing)
                    unique.append(article)
                break
        if not is_dup:
            unique.append(article)
    return unique


def cross_scan_dedup(articles):
    """Remove articles already seen in previous scans (via SQLite DB)."""
    if not HAS_DEDUP_DB:
        print("  Warning: dedup_db not available, skipping cross-scan dedup", file=sys.stderr)
        return articles

    db = DedupDB()
    article_dicts = [{"url": a["url"], "title": a["title"]} for a in articles]
    new_dicts, dupe_dicts, url_dupes, title_dupes = db.bulk_check(article_dicts)

    # Build set of new URLs for filtering
    new_urls = set()
    for d in new_dicts:
        new_urls.add(normalize_url(d["url"]))
    filtered = [a for a in articles if normalize_url(a["url"]) in new_urls]

    removed = len(articles) - len(filtered)
    if removed > 0:
        print("  Cross-scan dedup: removed %d (%d URL, %d title matches)" % (removed, url_dupes, title_dupes), file=sys.stderr)

    return filtered


def main():
    parser = argparse.ArgumentParser(description="Quality scoring pre-filter")
    parser.add_argument('--input', '-i', required=True, help='Input pipe-delimited file')
    parser.add_argument('--max', type=int, default=50, help='Max articles to output (default: 50)')
    parser.add_argument('--dedup-threshold', type=float, default=0.80,
                       help='Title similarity threshold for dedup (default: 0.80)')
    args = parser.parse_args()

    articles = []
    try:
        with open(args.input, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if len(parts) < 3:
                    continue
                title = parts[0]
                url = parts[1]
                source = parts[2]
                tier = parts[3] if len(parts) > 3 else ''

                score = compute_score(title, source, tier)
                articles.append({
                    'title': title,
                    'url': url,
                    'source': source,
                    'tier': tier,
                    'score': score,
                    'line': line,
                })
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1

    if not articles:
        print("No articles to score", file=sys.stderr)
        return 0

    articles.sort(key=lambda x: -x['score'])
    unique = deduplicate(articles, args.dedup_threshold)
    unique = cross_scan_dedup(unique)
    unique.sort(key=lambda x: -x['score'])
    output = unique[:args.max]

    for article in output:
        if article['tier']:
            print(f"{article['title']}|{article['url']}|{article['source']}|{article['tier']}")
        else:
            print(f"{article['title']}|{article['url']}|{article['source']}")

    total = len(articles)
    deduped = total - len(unique)
    final = len(output)
    print(f"  Done: {total} in -> {deduped} dupes removed -> {final} out", file=sys.stderr)


if __name__ == "__main__":
    main()
