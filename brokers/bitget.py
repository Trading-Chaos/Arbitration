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


EXCHANGE = "bitget"
BASE_URL = "https://api.bitget.com"


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("_", "").replace("-", "").removesuffix("SWAP")


def fetch_snapshot(
    symbol: str,
    product_type: str = "USDT-FUTURES",
    depth: str = "15",
    precision: str = "scale0",
    include_contract_config: bool = True,
    timeout: float = 10.0,
) -> MarketSnapshot:
    symbol = normalize_symbol(symbol)
    product_type = product_type.upper()

    ticker_payload, ticker_latency = http_get_json(
        BASE_URL,
        "/api/v2/mix/market/ticker",
        {"productType": product_type, "symbol": symbol},
        timeout=timeout,
    )
    ensure(ticker_payload.get("code") == "00000", "Bitget ticker request failed", ticker_payload)
    ticker = first(ticker_payload.get("data"))
    ensure(isinstance(ticker, dict), "Bitget ticker response has no symbol data", ticker_payload)

    book_payload, book_latency = http_get_json(
        BASE_URL,
        "/api/v2/mix/market/merge-depth",
        {
            "productType": product_type,
            "symbol": symbol,
            "limit": depth,
            "precision": precision,
        },
        timeout=timeout,
    )
    ensure(book_payload.get("code") == "00000", "Bitget depth request failed", book_payload)
    book = book_payload.get("data", {})
    ensure(isinstance(book, dict), "Bitget depth response has no data", book_payload)

    funding_payload, funding_latency = http_get_json(
        BASE_URL,
        "/api/v2/mix/market/current-fund-rate",
        {"productType": product_type, "symbol": symbol},
        timeout=timeout,
    )
    ensure(
        funding_payload.get("code") == "00000",
        "Bitget funding request failed",
        funding_payload,
    )
    funding = first(funding_payload.get("data"))
    ensure(isinstance(funding, dict), "Bitget funding response has no symbol data", funding_payload)

    oi_payload, oi_latency = http_get_json(
        BASE_URL,
        "/api/v2/mix/market/open-interest",
        {"productType": product_type, "symbol": symbol},
        timeout=timeout,
    )
    ensure(
        oi_payload.get("code") == "00000",
        "Bitget open interest request failed",
        oi_payload,
    )
    oi_list = oi_payload.get("data", {}).get("openInterestList", [])
    oi_item = first(oi_list)

    fees = Fees()
    config_latency = 0.0
    config = None
    if include_contract_config:
        config_payload, config_latency = http_get_json(
            BASE_URL,
            "/api/v2/mix/market/contracts",
            {"productType": product_type, "symbol": symbol},
            timeout=timeout,
        )
        ensure(
            config_payload.get("code") == "00000",
            "Bitget contract config request failed",
            config_payload,
        )
        config = first(config_payload.get("data"))
        if isinstance(config, dict):
            fees = Fees(
                maker=to_float(config.get("makerFeeRate")),
                taker=to_float(config.get("takerFeeRate")),
            )

    timestamp_ms = to_int(book.get("ts")) or to_int(ticker.get("ts"))
    orderbook = orderbook_from_rows(book.get("bids"), book.get("asks"), timestamp_ms)

    return MarketSnapshot(
        exchange=EXCHANGE,
        symbol=symbol,
        bid=to_float(ticker.get("bidPr")) or (orderbook.bids[0].price if orderbook.bids else None),
        ask=to_float(ticker.get("askPr")) or (orderbook.asks[0].price if orderbook.asks else None),
        last_price=to_float(ticker.get("lastPr")),
        mark_price=to_float(ticker.get("markPrice")),
        index_price=to_float(ticker.get("indexPrice")),
        funding_rate=to_float(funding.get("fundingRate")) or to_float(ticker.get("fundingRate")),
        next_funding_time_ms=to_int(funding.get("nextUpdate")),
        open_interest=to_float(oi_item.get("size")) if isinstance(oi_item, dict) else to_float(ticker.get("holdingAmount")),
        volume_24h=to_float(ticker.get("baseVolume")),
        quote_volume_24h=to_float(ticker.get("quoteVolume")) or to_float(ticker.get("usdtVolume")),
        fees=fees,
        latency_ms=round(ticker_latency + book_latency + funding_latency + oi_latency + config_latency, 3),
        timestamp_ms=timestamp_ms,
        orderbook=orderbook,
        raw={
            "ticker": ticker,
            "orderbook": book,
            "funding": funding,
            "open_interest": oi_payload.get("data"),
            "contract_config": config,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a Bitget market snapshot.")
    parser.add_argument("symbol", nargs="?", default="BTCUSDT")
    parser.add_argument("--product-type", default="USDT-FUTURES")
    parser.add_argument("--depth", default="15")
    parser.add_argument("--precision", default="scale0")
    args = parser.parse_args()
    print_snapshot(
        fetch_snapshot(args.symbol, args.product_type, args.depth, args.precision)
    )


if __name__ == "__main__":
    main()
