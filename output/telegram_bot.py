from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.spread_monitor import filter_rows
from src.spread_scanner import SpreadRow, scan_spreads, write_csv
from src.universe import exchange_names


TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_TELEGRAM_MESSAGE_LEN = 4096


class TelegramBotError(RuntimeError):
    """Raised when Telegram Bot API returns an unusable response."""


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def telegram_request(
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    body = json.dumps(payload or {}).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "spread-arbitrage-telegram-output/0.1",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise TelegramBotError(
            f"Telegram {method} failed with HTTP {exc.code}: {error_body[:500]}"
        ) from exc
    except URLError as exc:
        raise TelegramBotError(f"Telegram {method} failed: {exc.reason}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TelegramBotError(f"Telegram {method} returned invalid JSON") from exc

    if not isinstance(data, dict) or data.get("ok") is not True:
        raise TelegramBotError(f"Telegram {method} returned error: {data}")
    return data


def send_message(token: str, chat_id: str, text: str, timeout: float = 20.0) -> None:
    for chunk in split_message(text):
        telegram_request(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
            timeout=timeout,
        )


def get_chat_ids(token: str, timeout: float = 20.0) -> list[tuple[str, str]]:
    data = telegram_request(token, "getUpdates", timeout=timeout)
    chats: dict[str, str] = {}
    for update in data.get("result", []):
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("channel_post")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("id") is None:
            continue
        chat_id = str(chat["id"])
        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "chat"
        chats[chat_id] = str(title)
    return sorted(chats.items(), key=lambda item: item[1])


def build_alert_text(
    rows: list[SpreadRow],
    limit: int,
    started_at: datetime,
    top: int,
    min_spread: float,
    max_spread: float | None,
    min_volume: float | None,
) -> str:
    timestamp = started_at.strftime("%Y-%m-%d %H:%M:%S")
    shown = rows[:limit]
    lines = [
        f"Spread Arbitrage | {timestamp}",
        f"Top-{top} scan: найдено разлетов {len(rows)}",
        f"Filters: spread >= {min_spread:.4g}%, max <= {max_spread if max_spread is not None else 'off'}%, minVol24h >= {min_volume if min_volume is not None else 'off'}",
        "",
    ]

    if not shown:
        lines.append("Разлетов выше фильтров сейчас нет.")
        return "\n".join(lines)

    for index, row in enumerate(shown, start=1):
        lines.append(
            f"{index}. {row.base} | spread {row.spread_pct:.4f}%"
        )
        lines.append(
            f"   LONG {row.long_exchange} {row.long_symbol} ask={row.long_ask:.8g}"
        )
        lines.append(
            f"   SHORT {row.short_exchange} {row.short_symbol} bid={row.short_bid:.8g}"
        )
        lines.append(f"   minVol24h={row.min_quote_volume_24h:.2f}")

    if len(rows) > limit:
        lines.append("")
        lines.append(f"Еще {len(rows) - limit} строк скрыто лимитом Telegram-вывода.")

    return "\n".join(lines)


def collect_rows(args: argparse.Namespace) -> list[SpreadRow]:
    exchanges = exchange_names(args.exchanges)
    rows, _ = scan_spreads(
        exchanges=exchanges,
        quote=args.quote.upper(),
        top=args.top,
        timeout=args.timeout,
    )
    return filter_rows(
        rows,
        min_spread=args.min_spread,
        max_spread=args.max_spread,
        min_volume=args.min_volume,
    )


def run_once(args: argparse.Namespace, token: str | None, chat_id: str | None) -> list[SpreadRow]:
    started_at = datetime.now()
    rows = collect_rows(args)
    text = build_alert_text(
        rows=rows,
        limit=args.limit,
        started_at=started_at,
        top=args.top,
        min_spread=args.min_spread,
        max_spread=args.max_spread,
        min_volume=args.min_volume,
    )

    print(text)
    if args.csv:
        write_csv(Path(args.csv), rows)
        print(f"CSV saved: {args.csv}")

    if args.dry_run:
        print("Dry run: Telegram message was not sent.")
        return rows

    if not token:
        raise TelegramBotError("TELEGRAM_BOT_TOKEN is not set")
    if not chat_id:
        raise TelegramBotError("TELEGRAM_CHAT_ID is not set")

    send_message(token, chat_id, text, timeout=args.telegram_timeout)
    print("Telegram message sent.")
    return rows


def split_message(text: str) -> list[str]:
    if len(text) <= MAX_TELEGRAM_MESSAGE_LEN:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > MAX_TELEGRAM_MESSAGE_LEN:
            if current:
                chunks.append(current.rstrip())
                current = ""
            while len(line) > MAX_TELEGRAM_MESSAGE_LEN:
                chunks.append(line[:MAX_TELEGRAM_MESSAGE_LEN])
                line = line[MAX_TELEGRAM_MESSAGE_LEN:]
        current += line

    if current:
        chunks.append(current.rstrip())
    return chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send top spread alerts to Telegram every N seconds."
    )
    parser.add_argument("--exchanges", help="Comma-separated list, default: bybit,bitget,okx,mexc")
    parser.add_argument("--quote", default="USDT")
    parser.add_argument("--top", type=int, default=300)
    parser.add_argument("--interval", type=int, default=300, help="Seconds between Telegram alerts.")
    parser.add_argument("--limit", type=int, default=10, help="Max tickers per Telegram message.")
    parser.add_argument("--min-spread", type=float, default=0.3)
    parser.add_argument("--max-spread", type=float, default=5.0)
    parser.add_argument("--min-volume", type=float, default=1_000_000)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--telegram-timeout", type=float, default=20.0)
    parser.add_argument("--csv", default="data/telegram_spreads_latest.csv")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--bot-token", default=None)
    parser.add_argument("--chat-id", default=None)
    parser.add_argument("--once", action="store_true", help="Send one Telegram alert and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print message without sending it.")
    parser.add_argument("--get-chat-id", action="store_true", help="Print chat IDs from recent bot updates.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    load_env_file(args.env)

    token = args.bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = args.chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if args.get_chat_id:
        if not token:
            raise TelegramBotError("TELEGRAM_BOT_TOKEN is not set")
        chats = get_chat_ids(token, timeout=args.telegram_timeout)
        if not chats:
            print("No chats found. Send any message to the bot, then run this again.")
            return
        for found_chat_id, title in chats:
            print(f"{found_chat_id} {title}")
        return

    if args.once:
        run_once(args, token, chat_id)
        return

    print(
        "Telegram spread bot started: "
        f"top={args.top}, interval={args.interval}s, limit={args.limit}, "
        f"min_spread={args.min_spread}%, max_spread={args.max_spread}%, "
        f"min_volume={args.min_volume}"
    )
    while True:
        try:
            run_once(args, token, chat_id)
        except Exception as exc:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Telegram bot check failed: {type(exc).__name__}: {exc}")
        sleep(args.interval)


if __name__ == "__main__":
    main()
