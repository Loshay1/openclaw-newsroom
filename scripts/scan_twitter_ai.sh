#!/bin/bash
# Twitter/X AI News Scanner
# Scans official accounts, reporters/leakers, and trending AI topics
# Requires: bird CLI — https://bird.fast
# Install: npm install -g @steipete/bird  OR  brew install steipete/tap/bird

set -e

BIRD="/usr/local/bin/bird"

# Auth check: bird reads AUTH_TOKEN and CT0 from env vars automatically.
# If not in env (e.g., SSH session), fall back to Chrome cookies.
if [ -z "$AUTH_TOKEN" ] || [ -z "$CT0" ]; then
  if [ -d "$HOME/Library/Application Support/Google/Chrome" ]; then
    BIRD_EXTRA="--cookie-source chrome"
  else
    echo "Warning: No X auth available (no AUTH_TOKEN/CT0 env vars, no Chrome cookies)"
    echo "Twitter scan skipped."
    exit 0
  fi
else
  BIRD_EXTRA=""
fi

echo "Scanning X/Twitter for trading news..."

# Tier 1: Must-follow accounts (fastest market signals)
OFFICIAL_ACCOUNTS=(
  "unusual_whales"
  "DeItaone"
  "Newsquawk"
)

# Tier 2: Analysts and trade idea accounts
REPORTER_ACCOUNTS=(
  "OptionsAction"
  "PeterLBrandt"
  "MarkMinervini"
)

# Tier 3: Context — macro, metals, crypto
CEO_ACCOUNTS=(
  "zaboramus"
  "GoldTelegraph_"
  "WatcherGuru"
  "CoinDesk"
)

echo "Scanning official accounts..."
for acct in "${OFFICIAL_ACCOUNTS[@]}"; do
  timeout 8s $BIRD $BIRD_EXTRA search "from:$acct" -n 3 --plain 2>/dev/null | head -20 || true
done

echo ""
echo "Scanning reporters & leakers..."
for acct in "${REPORTER_ACCOUNTS[@]}"; do
  timeout 8s $BIRD $BIRD_EXTRA search "from:$acct" -n 3 --plain 2>/dev/null | head -20 || true
done

echo ""
echo "Breaking market news search..."
timeout 10s $BIRD $BIRD_EXTRA search unusual options activity OR whale OR dark pool OR block trade -filter:replies -filter:retweets -n 8 --plain 2>/dev/null | head -40 || true

echo ""
echo "Macro & metals signals..."
timeout 10s $BIRD $BIRD_EXTRA search Fed rate OR gold breakout OR silver OR CPI OR tariff -filter:replies -filter:retweets -n 8 --plain 2>/dev/null | head -40 || true

echo ""
echo "Crypto & context signals..."
for acct in "${CEO_ACCOUNTS[@]}"; do
  timeout 8s $BIRD $BIRD_EXTRA search "from:$acct" -n 2 --plain 2>/dev/null | head -15 || true
done
