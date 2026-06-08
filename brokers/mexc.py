from __future__ import annotations

import argparse
from typing import Any

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


EXCHANGE = "mexc"
BASE_URL = "https://contract.mexc.com"


def normalize_symbol(symbol: str, quote: str = "USDT") -> str:
    value = symbol.upper().strip().replace("-", "_")
    if value.endswith("_SWAP"):
        value = value.removesuffix("_SWAP")
    if "_" in value:
        return value
    if value.endswith(quote):
        return f"{value[:-len(quote)]}_{quote}"
    return value


def fetch_snapshot(
    symbol: str,
    depth: int = 20,
    include_contract_detail: bool = True,
    timeout: float = 10.0,
) -> MarketSnapshot:
    symbol = normalize_symbol(symbol)

    ticker_payload, ticker_latency = http_get_json(
        BASE_URL,
        "/api/v1/contract/ticker",
        {"symbol": symbol},
        timeout=timeout,
    )
    ensure(ticker_payload.get("success") is True, "MEXC ticker request failed", ticker_payload)
    ticker_data = ticker_payload.get("data")
    ticker = first(ticker_data) if isinstance(ticker_data, list) else ticker_data
    ensure(isinstance(ticker, dict), "MEXC ticker response has no symbol data", ticker_payload)

    book_payload, book_latency = http_get_json(
        BASE_URL,
        f"/api/v1/contract/depth/{symbol}",
        {"limit": depth},
        timeout=timeout,
    )
    ensure(book_payload.get("success") is True, "MEXC depth request failed", book_payload)
    book = book_payload.get("data", {})
    ensure(isinstance(book, dict), "MEXC depth response has no data", book_payload)

    fees = Fees()
    detail_latency = 0.0
    detail: dict[str, Any] | None = None
    if include_contract_detail:
        detail_payload, detail_latency = http_get_json(
            BASE_URL,
            "/api/v1/contract/detail",
            {"symbol": symbol},
            timeout=timeout,
        )
        ensure(detail_payload.get("success") is True, "MEXC contract detail request failed", detail_payload)
        detail_data = detail_payload.get("data")
        detail = first(detail_data) if isinstance(detail_data, list) else detail_data
        if isinstance(detail, dict):
            fees = Fees(
                maker=to_float(detail.get("makerFeeRate")),
                taker=to_float(detail.get("takerFeeRate")),
            )

    timestamp_ms = to_int(book.get("timestamp")) or to_int(ticker.get("timestamp"))
    orderbook = orderbook_from_rows(book.get("bids"), book.get("asks"), timestamp_ms)

    return MarketSnapshot(
        exchange=EXCHANGE,
        symbol=symbol,
        bid=to_float(ticker.get("bid1")) or (orderbook.bids[0].price if orderbook.bids else None),
        ask=to_float(ticker.get("ask1")) or (orderbook.asks[0].price if orderbook.asks else None),
        last_price=to_float(ticker.get("lastPrice")),
        mark_price=to_float(ticker.get("fairPrice")),
        index_price=to_float(ticker.get("indexPrice")),
        funding_rate=to_float(ticker.get("fundingRate")),
        next_funding_time_ms=None,
        open_interest=to_float(ticker.get("holdVol")),
        volume_24h=to_float(ticker.get("volume24")),
        quote_volume_24h=to_float(ticker.get("amount24")),
        fees=fees,
        latency_ms=round(ticker_latency + book_latency + detail_latency, 3),
        timestamp_ms=timestamp_ms,
        orderbook=orderbook,
        raw={"ticker": ticker, "orderbook": book, "contract_detail": detail},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a MEXC futures market snapshot.")
    parser.add_argument("symbol", nargs="?", default="BTC_USDT")
    parser.add_argument("--depth", type=int, default=20)
    args = parser.parse_args()
    print_snapshot(fetch_snapshot(args.symbol, args.depth))


if __name__ == "__main__":
    main()
