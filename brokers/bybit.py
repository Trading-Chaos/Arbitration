from __future__ import annotations

import argparse

from .common import (
    Fees,
    MarketSnapshot,
    ensure,
    first,
    http_get_json,
    orderbook_from_rows,
    print_snapshot,
    to_float,
    to_int,
)


EXCHANGE = "bybit"
BASE_URL = "https://api.bybit.com"
TESTNET_BASE_URL = "https://api-testnet.bybit.com"


def normalize_symbol(symbol: str) -> str:
    value = symbol.upper().strip().replace("_", "-")
    if value.endswith("-SWAP"):
        value = value.removesuffix("-SWAP")
    return value.replace("-", "")


def fetch_snapshot(
    symbol: str,
    category: str = "linear",
    depth: int = 25,
    testnet: bool = False,
    timeout: float = 10.0,
) -> MarketSnapshot:
    symbol = normalize_symbol(symbol)
    base_url = TESTNET_BASE_URL if testnet else BASE_URL

    ticker_payload, ticker_latency = http_get_json(
        base_url,
        "/v5/market/tickers",
        {"category": category, "symbol": symbol},
        timeout=timeout,
    )
    ensure(ticker_payload.get("retCode") == 0, "Bybit ticker request failed", ticker_payload)
    ticker = first(ticker_payload.get("result", {}).get("list"))
    ensure(isinstance(ticker, dict), "Bybit ticker response has no symbol data", ticker_payload)

    book_payload, book_latency = http_get_json(
        base_url,
        "/v5/market/orderbook",
        {"category": category, "symbol": symbol, "limit": depth},
        timeout=timeout,
    )
    ensure(book_payload.get("retCode") == 0, "Bybit orderbook request failed", book_payload)
    book = book_payload.get("result", {})
    ensure(isinstance(book, dict), "Bybit orderbook response has no result", book_payload)

    timestamp_ms = to_int(book.get("ts")) or to_int(ticker_payload.get("time"))
    orderbook = orderbook_from_rows(book.get("b"), book.get("a"), timestamp_ms)
    bid = to_float(ticker.get("bid1Price")) or (orderbook.bids[0].price if orderbook.bids else None)
    ask = to_float(ticker.get("ask1Price")) or (orderbook.asks[0].price if orderbook.asks else None)

    return MarketSnapshot(
        exchange=EXCHANGE,
        symbol=symbol,
        bid=bid,
        ask=ask,
        last_price=to_float(ticker.get("lastPrice")),
        mark_price=to_float(ticker.get("markPrice")),
        index_price=to_float(ticker.get("indexPrice")),
        funding_rate=to_float(ticker.get("fundingRate")),
        next_funding_time_ms=to_int(ticker.get("nextFundingTime")),
        open_interest=to_float(ticker.get("openInterest")),
        volume_24h=to_float(ticker.get("volume24h")),
        quote_volume_24h=to_float(ticker.get("turnover24h")),
        fees=Fees(),
        latency_ms=round(ticker_latency + book_latency, 3),
        timestamp_ms=timestamp_ms,
        orderbook=orderbook,
        raw={"ticker": ticker, "orderbook": book},
    )


def fetch_open_interest(
    symbol: str,
    category: str = "linear",
    interval: str = "5min",
    timeout: float = 10.0,
) -> float | None:
    payload, _ = http_get_json(
        BASE_URL,
        "/v5/market/open-interest",
        {
            "category": category,
            "symbol": normalize_symbol(symbol),
            "intervalTime": interval,
            "limit": 1,
        },
        timeout=timeout,
    )
    ensure(payload.get("retCode") == 0, "Bybit open interest request failed", payload)
    item = first(payload.get("result", {}).get("list"))
    return to_float(item.get("openInterest")) if isinstance(item, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a Bybit market snapshot.")
    parser.add_argument("symbol", nargs="?", default="BTCUSDT")
    parser.add_argument("--category", default="linear")
    parser.add_argument("--depth", type=int, default=25)
    parser.add_argument("--testnet", action="store_true")
    args = parser.parse_args()
    print_snapshot(fetch_snapshot(args.symbol, args.category, args.depth, args.testnet))


if __name__ == "__main__":
    main()
