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


EXCHANGE = "okx"
BASE_URL = "https://www.okx.com"


def normalize_symbol(symbol: str, quote: str = "USDT") -> str:
    value = symbol.upper().strip().replace("_", "-")
    if value.endswith("-SWAP"):
        return value
    if "-" in value:
        return f"{value}-SWAP" if value.endswith(f"-{quote}") else value
    if value.endswith(quote):
        return f"{value[:-len(quote)]}-{quote}-SWAP"
    return value


def fetch_snapshot(
    symbol: str,
    inst_type: str = "SWAP",
    depth: int = 25,
    base_url: str = BASE_URL,
    timeout: float = 10.0,
) -> MarketSnapshot:
    symbol = normalize_symbol(symbol)
    inst_type = inst_type.upper()

    ticker_payload, ticker_latency = http_get_json(
        base_url,
        "/api/v5/market/ticker",
        {"instId": symbol},
        timeout=timeout,
    )
    ensure(ticker_payload.get("code") == "0", "OKX ticker request failed", ticker_payload)
    ticker = first(ticker_payload.get("data"))
    ensure(isinstance(ticker, dict), "OKX ticker response has no symbol data", ticker_payload)

    book_payload, book_latency = http_get_json(
        base_url,
        "/api/v5/market/books",
        {"instId": symbol, "sz": depth},
        timeout=timeout,
    )
    ensure(book_payload.get("code") == "0", "OKX orderbook request failed", book_payload)
    book = first(book_payload.get("data"))
    ensure(isinstance(book, dict), "OKX orderbook response has no data", book_payload)

    funding_payload, funding_latency = http_get_json(
        base_url,
        "/api/v5/public/funding-rate",
        {"instId": symbol},
        timeout=timeout,
    )
    ensure(funding_payload.get("code") == "0", "OKX funding request failed", funding_payload)
    funding = first(funding_payload.get("data"))
    ensure(isinstance(funding, dict), "OKX funding response has no symbol data", funding_payload)

    mark_payload, mark_latency = http_get_json(
        base_url,
        "/api/v5/public/mark-price",
        {"instType": inst_type, "instId": symbol},
        timeout=timeout,
    )
    ensure(mark_payload.get("code") == "0", "OKX mark price request failed", mark_payload)
    mark = first(mark_payload.get("data"))

    oi_payload, oi_latency = http_get_json(
        base_url,
        "/api/v5/public/open-interest",
        {"instType": inst_type, "instId": symbol},
        timeout=timeout,
    )
    ensure(oi_payload.get("code") == "0", "OKX open interest request failed", oi_payload)
    oi = first(oi_payload.get("data"))

    timestamp_ms = to_int(book.get("ts")) or to_int(ticker.get("ts"))
    orderbook = orderbook_from_rows(book.get("bids"), book.get("asks"), timestamp_ms)

    return MarketSnapshot(
        exchange=EXCHANGE,
        symbol=symbol,
        bid=to_float(ticker.get("bidPx")) or (orderbook.bids[0].price if orderbook.bids else None),
        ask=to_float(ticker.get("askPx")) or (orderbook.asks[0].price if orderbook.asks else None),
        last_price=to_float(ticker.get("last")),
        mark_price=to_float(mark.get("markPx")) if isinstance(mark, dict) else None,
        index_price=None,
        funding_rate=to_float(funding.get("fundingRate")),
        next_funding_time_ms=to_int(funding.get("nextFundingTime")),
        open_interest=to_float(oi.get("oi")) if isinstance(oi, dict) else None,
        volume_24h=to_float(ticker.get("vol24h")),
        quote_volume_24h=to_float(ticker.get("volCcy24h")),
        fees=Fees(),
        latency_ms=round(ticker_latency + book_latency + funding_latency + mark_latency + oi_latency, 3),
        timestamp_ms=timestamp_ms,
        orderbook=orderbook,
        raw={
            "ticker": ticker,
            "orderbook": book,
            "funding": funding,
            "mark_price": mark,
            "open_interest": oi,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch an OKX market snapshot.")
    parser.add_argument("symbol", nargs="?", default="BTC-USDT-SWAP")
    parser.add_argument("--inst-type", default="SWAP")
    parser.add_argument("--depth", type=int, default=25)
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()
    print_snapshot(fetch_snapshot(args.symbol, args.inst_type, args.depth, args.base_url))


if __name__ == "__main__":
    main()
