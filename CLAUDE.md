# openclaw-newsroom

Forked from jacob-bd/openclaw-newsroom. Customized as **Larab's Trade Desk** — an actionable trade idea engine, not a generic news feed.

## What This Does

Scans 5 sources on a cron schedule, scores/deduplicates via SQLite, curates picks through a 3-tier LLM failover chain (Gemini Flash Lite -> Grok -> Gemini Flash), and delivers individual formatted articles + summary digest to Telegram.

## Topic Focus

- **Primary:** Options flow, crypto (BTC/ETH/SOL/alts), precious metals (gold/silver)
- **Secondary:** Legal tech AI, Home Assistant
- **Meta:** Geopolitical catalysts, macro events (Fed, CPI, tariffs)

## Deployment

- **Node:** Bashir (Beelink WSL2)
- **Scripts:** `~/.openclaw/workspace/scripts/`
- **Memory:** `~/.openclaw/workspace/memory/`
- **Env:** `~/.openclaw/workspace/.env` (API keys, Telegram bot token, bird auth)
- **Telegram bot:** @ApnaGeoNewsBot
- **Cron:** Pre-market+market hourly 5am-4pm CT M-F, off-hours 3x/day, weekends every 4h

## Key Files

| File | Purpose |
|------|---------|
| `config/editorial_profile.md` | LLM reads this every scan — editorial voice and rules |
| `config/newsroom_config.yaml` | Full config from interview session |
| `scripts/news_scan_deduped.sh` | Main orchestrator — runs all 5 sources |
| `scripts/run_newsroom.sh` | Wrapper that sources .env before running orchestrator |
| `scripts/llm_editor.py` | 3-tier LLM failover chain, rich article output format |
| `scripts/telegram_deliver.py` | Sends individual articles + summary to Telegram |
| `scripts/quality_score.py` | Scoring with trading keyword boosts/penalties |
| `scripts/fetch_reddit_news.py` | Reddit scanner with RSS fallback for IP-blocked hosts |
| `scripts/scan_twitter_ai.sh` | Twitter/X bird CLI (financial accounts) |
| `scripts/fetch_twitter_api.py` | twitterapi.io keyword search (optional) |
| `scripts/fetch_web_news.py` | Tavily web search supplement |
| `scripts/filter_ai_news.sh` | RSS keyword filter (standalone) |

## Conventions

- Python: stdlib only (no pip). Type hints preferred.
- Shell: `set -e`. All sources are best-effort (failures don't kill pipeline).
- Output: pipe-delimited `TITLE|URL|SOURCE` format between stages.
- LLM output: JSON with rank, title, url, source, type, category, emoji, facts[], why_it_matters, trade_play, one_liner.
- Telegram: individual MarkdownV2 messages per article + summary digest.
- Binaries: PATH-relative (`timeout`, `blogwatcher`, `bird`) for Mac/Linux compatibility.

## Environment Variables (Bashir .env)

| Variable | Purpose | Source |
|----------|---------|--------|
| `GEMINI_API_KEY` | LLM curation (primary + fallback) | 1Password OpenClaw vault |
| `OPENROUTER_API_KEY` | LLM failover (Grok) | 1Password OpenClaw vault |
| `GH_TOKEN` | GitHub trending API | `gh auth token` |
| `TAVILY_API_KEY` | Web search | 1Password OpenClaw vault |
| `AUTH_TOKEN` | bird CLI X/Twitter auth | Safari cookies (Mac) |
| `CT0` | bird CLI X/Twitter auth | Safari cookies (Mac) |
| `TELEGRAM_BOT_TOKEN` | Telegram delivery | @BotFather |
| `TELEGRAM_CHAT_ID` | Telegram recipient | `6359543542` |

## Running Locally

```bash
cd scripts
./news_scan_deduped.sh --top 5
```

## Running on Bashir

```bash
ssh beelink "wsl bash -c 'bash ~/.openclaw/workspace/scripts/run_newsroom.sh --top 5'"
```

## Deploying Changes

```bash
# From ~/Projects/openclaw-newsroom/
scp scripts/CHANGED_FILE.py "beelink:C:\\Temp\\CHANGED_FILE.py"
ssh beelink "wsl bash -c 'cp /mnt/c/Temp/CHANGED_FILE.py ~/.openclaw/workspace/scripts/'"
```

## Upstream Sync

```bash
git fetch upstream
git merge upstream/main
```

Resolve conflicts in customized files (keywords, accounts, scoring weights, LLM prompt).

## Known Issues

- **Reddit:** Beelink IP blocked by Reddit (403). RSS fallback code deployed but also rate-limited. Will recover on its own; may need proxy for reliable access.
- **bird token rotation:** Safari cookies expire periodically. Re-extract from Mac Safari and update Bashir .env.
- **4 dropped RSS feeds:** Unusual Whales, Kitco, Gold.org, Law.com have no public RSS.
