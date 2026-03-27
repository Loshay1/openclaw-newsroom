#!/usr/bin/env python3
"""
telegram_deliver.py - Send newsroom picks to Telegram as individual articles + summary.

Reads JSON picks from llm_editor.py output (one JSON object per line) and sends
each as a formatted Telegram message, followed by a summary digest.

Usage:
    python3 telegram_deliver.py --file picks.json

Environment:
    TELEGRAM_BOT_TOKEN — required
    TELEGRAM_CHAT_ID   — required (default: reads from --chat-id flag)
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[telegram {ts}] {msg}", file=sys.stderr)


def escape_md2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r'_*[]()~`>#+-=|{}.!'
    result = []
    for ch in text:
        if ch in special:
            result.append('\\')
        result.append(ch)
    return ''.join(result)


def send_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "MarkdownV2") -> bool:
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        log(f"  Telegram API error {e.code}: {body}")
        return False
    except Exception as e:
        log(f"  Telegram send failed: {e}")
        return False


def format_article(pick: dict) -> str:
    """Format a single pick as a Telegram MarkdownV2 message."""
    emoji = pick.get("emoji", "")
    title = escape_md2(pick.get("title", "(no title)"))
    source = pick.get("source", "unknown")
    url = pick.get("url", "")
    facts = pick.get("facts", [])
    why = pick.get("why_it_matters", "")
    play = pick.get("trade_play", "")

    lines = [f"{emoji} *{title}*", ""]

    for fact in facts:
        lines.append(escape_md2(fact))
        lines.append("")

    if why:
        lines.append(f"\U0001f4a1 *Why this matters:*")
        lines.append(escape_md2(why))
        lines.append("")

    if play:
        lines.append(f"\U0001f4ca *The play:* {escape_md2(play)}")
        lines.append("")

    if url:
        source_clean = escape_md2(source.replace(" (tweet)", ""))
        lines.append(f"Source: [{source_clean}]({url})")

    return "\n".join(lines)


def format_summary(picks: list, stats: dict) -> str:
    """Format the summary digest message."""
    lines = [
        f"\U0001f4e1 *Larab's Trade Desk — Scan Summary*",
        escape_md2("━" * 30),
        "",
    ]

    for pick in picks:
        emoji = pick.get("emoji", "")
        one_liner = escape_md2(pick.get("one_liner", pick.get("title", "")))
        lines.append(f"{emoji} {one_liner}")

    lines.append("")
    lines.append(escape_md2("━" * 30))

    raw = stats.get("raw", "?")
    scored = stats.get("scored", "?")
    count = len(picks)
    sources = stats.get("sources", "")
    lines.append(escape_md2(f"{raw} scanned | {scored} scored | {count} picks"))
    if sources:
        lines.append(escape_md2(f"Sources: {sources}"))

    now = datetime.now().strftime("%b %d, %Y — %I:%M %p")
    lines.append(escape_md2(now))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send newsroom picks to Telegram")
    parser.add_argument("--file", "-f", required=True, help="Path to picks JSON (one per line)")
    parser.add_argument("--chat-id", default="", help="Telegram chat ID")
    parser.add_argument("--stats", default="", help="Pipeline stats as JSON string")
    parser.add_argument("--dry-run", action="store_true", help="Print messages without sending")
    args = parser.parse_args()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token and not args.dry_run:
        log("ERROR: TELEGRAM_BOT_TOKEN not set")
        return 1
    if not chat_id and not args.dry_run:
        log("ERROR: TELEGRAM_CHAT_ID not set (use --chat-id or TELEGRAM_CHAT_ID env)")
        return 1

    # Load picks
    picks = []
    try:
        with open(args.file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    picks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        log(f"ERROR: File not found: {args.file}")
        return 1

    if not picks:
        log("No picks to deliver")
        return 0

    # Parse stats
    stats = {}
    if args.stats:
        try:
            stats = json.loads(args.stats)
        except json.JSONDecodeError:
            pass

    log(f"Delivering {len(picks)} picks to Telegram chat {chat_id}")

    # Send individual articles
    sent = 0
    for pick in picks:
        msg = format_article(pick)
        if args.dry_run:
            print(f"--- Article {pick.get('rank', '?')} ---")
            print(msg)
            print()
            sent += 1
        else:
            if send_message(bot_token, chat_id, msg):
                sent += 1
                time.sleep(1)  # Rate limit: 1 msg/sec
            else:
                log(f"  Failed to send article {pick.get('rank', '?')}")

    # Send summary
    summary = format_summary(picks, stats)
    if args.dry_run:
        print("--- Summary ---")
        print(summary)
    else:
        time.sleep(1)
        if send_message(bot_token, chat_id, summary):
            sent += 1
        else:
            log("  Failed to send summary")

    log(f"Done: {sent}/{len(picks) + 1} messages sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
