#!/bin/bash
# AI News Filter for the News Scan Pipeline
# Entry-based filtering with source tiers and Reddit noise filter
# Output: TITLE|URL|SOURCE|TIER (pipe-delimited, sorted by tier)
# Requires: blogwatcher CLI

python3 << 'PYEOF'
import subprocess, sys, re

result = subprocess.run(
    ['blogwatcher', 'articles'],
    capture_output=True, text=True, timeout=90
)
raw = result.stdout

# ── Keywords ─────────────────────────────────────────────────────────
# Short keywords (<=3 chars) need word boundaries to prevent substring matches
SHORT_KEYWORDS = ['SPY', 'QQQ', 'IWM', 'GLD', 'SLV', 'BTC', 'ETH', 'SOL', 'Fed', 'CPI', 'GDP', 'IPO', 'SEC']

LONG_KEYWORDS = [
    'options', 'unusual activity', 'whale', 'dark pool', 'block trade',
    'earnings', 'bull call spread', 'put credit spread', 'iron condor',
    'risk reward', 'breakout', 'catalyst', 'swing trade',
    'NVDA', 'TSLA', 'AAPL', 'AMZN', 'AMD', 'META', 'MSFT', 'GOOG', 'PLTR', 'SNAP',
    'MSTR', 'COIN', 'BITO',
    'gold', 'silver', 'platinum', 'palladium', 'precious metal',
    'GDX', 'GDXJ', 'Kitco',
    'bitcoin', 'ethereum', 'solana', 'crypto', 'DeFi', 'memecoin', 'altcoin',
    'Federal Reserve', 'rate decision', 'interest rate', 'inflation',
    'tariff', 'sanctions', 'geopolitical', 'OPEC', 'trade war',
    'legal tech', 'legal AI', 'court ruling',
    'Home Assistant', 'smart home',
    'acquisition', 'merger', 'funding', 'valuation',
    'launch', 'release',
]

EXCLUDE_KEYWORDS = [
    'paid course', 'join my discord', 'guaranteed returns',
    'penny stock', 'pump and dump',
    'podcast', 'interview', 'conference announcement',
]

# Build combined pattern: word-bounded short keywords + substring long keywords
short_pat = r'\b(' + '|'.join(re.escape(k) for k in SHORT_KEYWORDS) + r')\b'
long_pat = '|'.join(re.escape(k) for k in sorted(LONG_KEYWORDS, key=len, reverse=True))
ai_pattern = re.compile(short_pat + '|' + long_pat, re.IGNORECASE)

exclude_pattern = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in EXCLUDE_KEYWORDS) + r')\b',
    re.IGNORECASE
)

# ── Source tiers (names must match blogwatcher exactly) ──────────────
# Customize: add your RSS feed names here with their trust tier
SOURCE_TIERS = {
    # T1: Wire services + flow data + metals
    'Bloomberg Markets': 1, 'Reuters Business': 1, 'Federal Reserve Press Releases': 1,
    'Unusual Whales Flow': 1, 'CoinDesk': 1, 'Kitco News': 1,
    'Home Assistant Blog': 1, 'Artificial Lawyer': 1,
    # T2: Financial press + legal + crypto
    'CNBC Options Action': 2, 'MarketWatch Top Stories': 2,
    'Seeking Alpha Market News': 2, 'The Block': 2,
    'Above the Law': 2, 'AP News World': 2, 'Law.com Legal Tech': 2,
    'ABA Journal Tech': 2, 'Gold.org (World Gold Council)': 2, 'Decrypt': 2,
    # T3: Aggregators
    'Zero Hedge': 3,
}

# Reddit discussion noise (questions, complaints, memes)
REDDIT_NOISE_START = re.compile(
    r'^(Why|How|What|Can|Does|Is|Has|Are|Do|Should|Would|Could|Anyone|'
    r'Help|Rant|Vent|Am I|ELI5|CMV|PSA|Unpopular|Hot take|DAE|TIL|'
    r'Gah|Kindly explain|Seriously|From Frustration|Gemini Memory)',
    re.IGNORECASE
)

def get_tier(source, title):
    if source in SOURCE_TIERS:
        return SOURCE_TIERS[source]
    if source.startswith('r/') or 'reddit.com' in source:
        title_s = title.strip()
        if REDDIT_NOISE_START.match(title_s):
            return 99
        if title_s.endswith('?'):
            return 99
        if len(title_s) < 20:
            return 99
        return 4
    if source.startswith('http'):
        if 'bloomberg.com' in source: return 1
        if 'cnbc.com' in source: return 1
        if 'reuters.com' in source: return 1
        if 'techcrunch.com' in source: return 2
        if 'theverge.com' in source: return 2
        if 'wired.com' in source: return 2
        return 3
    return 3

# ── Parse blogwatcher entries ────────────────────────────────────────
title = url = source = None
results = []

for line in raw.split('\n'):
    stripped = line.strip()

    m = re.match(r'\[(\d+)\]\s*\[new\]\s*(.*)', stripped)
    if m:
        if title and url and source is not None:
            tier = get_tier(source, title)
            if tier != 99:
                if ai_pattern.search(title) and not exclude_pattern.search(title):
                    results.append((title, url, source, tier))
        title = m.group(2).strip()
        url = source = None
        continue

    if stripped.startswith('Blog:'):
        source = stripped[5:].strip()
    elif stripped.startswith('URL:'):
        url = stripped[4:].strip()

if title and url and source is not None:
    tier = get_tier(source, title)
    if tier != 99:
        if ai_pattern.search(title) and not exclude_pattern.search(title):
            results.append((title, url, source, tier))

results.sort(key=lambda x: x[3])

for t, u, s, tier in results:
    t_clean = t.replace('|', ' —')
    print(f"{t_clean}|{u}|{s}|{tier}")
PYEOF
