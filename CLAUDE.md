# openclaw-newsroom

Forked from jacob-bd/openclaw-newsroom. Customized as a **trade idea engine** (not a generic news feed).

## What This Does

Automated pipeline scans 5 sources every 1-4 hours, scores/deduplicates, and curates actionable trade ideas via LLM editorial filter. Delivers to Telegram.

## Topic Focus

- **Primary:** Options flow, crypto (BTC/ETH/SOL/alts), precious metals (gold/silver)
- **Secondary:** Legal tech AI, Home Assistant
- **Meta:** Geopolitical catalysts, macro events (Fed, CPI, tariffs)

## Key Files

| File | Purpose |
|------|---------|
| `config/editorial_profile.md` | LLM reads this every scan — editorial voice and rules |
| `config/newsroom_config.yaml` | Full config from interview session |
| `scripts/news_scan_deduped.sh` | Main orchestrator — runs all 5 sources |
| `scripts/llm_editor.py` | 3-tier LLM failover chain for curation |
| `scripts/quality_score.py` | Scoring with trading keyword boosts/penalties |
| `scripts/fetch_reddit_news.py` | Reddit scanner (12 trading/crypto/legal/HA subs) |
| `scripts/scan_twitter_ai.sh` | Twitter/X bird CLI (financial accounts) |
| `scripts/fetch_twitter_api.py` | twitterapi.io keyword search |
| `scripts/fetch_web_news.py` | Tavily web search supplement |
| `scripts/filter_ai_news.sh` | RSS keyword filter (standalone) |

## Conventions

- Python: stdlib only (no pip). Type hints preferred.
- Shell: `set -e`. All sources are best-effort (failures don't kill pipeline).
- Output: pipe-delimited `TITLE|URL|SOURCE` format between stages.
- LLM output: JSON array with rank, title, url, source, type, summary, category.

## Running Locally

```bash
cd scripts
./news_scan_deduped.sh --top 5
```

## Upstream Sync

```bash
git fetch upstream
git merge upstream/main
```

Resolve conflicts in customized files (keywords, accounts, scoring weights).
