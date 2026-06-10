from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Callable

from brokers import bitget, bybit, mexc, okx
from brokers.common import JsonObject, ensure, http_get_json, to_float, to_int


DEFAULT_EXCHANGES = ("bybit", "bitget", "okx", "mexc")


@dataclass(frozen=True)
class TickerQuote:
    exchange: str
    symbol: str
    base: str
    quote: str
    bid: float | None
    ask: float | None
    last_price: float | None
    mark_price: float | None
    funding_rate: float | None
    open_interest: float | None
    volume_24h: float | None
    quote_volume_24h: float | None
    timestamp_ms: int | None
    raw: JsonObject = field(repr=False)


@dataclass(frozen=True)
class ExchangeUniverse:
    exchange: str
    tickers: list[TickerQuote]
    latency_ms: float


def fetch_exchange_universe(
    exchange: str,
    quote: str = "USDT",
    timeout: float = 10.0,
) -> ExchangeUniverse:
    exchange = exchange.lower()
    fetchers: dict[str, Callable[[str, float], ExchangeUniverse]] = {
        "bybit": fetch_bybit_universe,
        "bitget": fetch_bitget_universe,
        "okx": fetch_okx_universe,
        "mexc": fetch_mexc_universe,
    }
    if exchange not in fetchers:
        raise ValueError(f"Unknown exchange: {exchange}")
    return fetchers[exchange](quote, timeout)


def fetch_bybit_universe(quote: str = "USDT", timeout: float = 10.0) -> ExchangeUniverse:
    started = perf_counter()
    payload, _ = http_get_json(
        bybit.BASE_URL,
        "/v5/market/tickers",
        {"category": "linear"},
        timeout=timeout,
    )
    ensure(payload.get("retCode") == 0, "Bybit ticker universe request failed", payload)

    tickers: list[TickerQuote] = []
    for item in payload.get("result", {}).get("list", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper()
        if not symbol.endswith(quote):
            continue
        tickers.append(
            TickerQuote(
                exchange=bybit.EXCHANGE,
                symbol=symbol,
                base=symbol.removesuffix(quote),
                quote=quote,
                bid=to_float(item.get("bid1Price")),
                ask=to_float(item.get("ask1Price")),
                last_price=to_float(item.get("lastPrice")),
                mark_price=to_float(item.get("markPrice")),
                funding_rate=to_float(item.get("fundingRate")),
                open_interest=to_float(item.get("openInterest")),
                volume_24h=to_float(item.get("volume24h")),
                quote_volume_24h=to_float(item.get("turnover24h")),
                timestamp_ms=to_int(payload.get("time")),
                raw=item,
            )
        )

    return ExchangeUniverse(
        exchange=bybit.EXCHANGE,
        tickers=tickers,
        latency_ms=round((perf_counter() - started) * 1000, 3),
    )


def fetch_bitget_universe(quote: str = "USDT", timeout: float = 10.0) -> ExchangeUniverse:
    started = perf_counter()
    payload, _ = http_get_json(
        bitget.BASE_URL,
        "/api/v2/mix/market/tickers",
        {"productType": f"{quote}-FUTURES"},
        timeout=timeout,
    )
    ensure(payload.get("code") == "00000", "Bitget ticker universe request failed", payload)

    tickers: list[TickerQuote] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper()
        if not symbol.endswith(quote):
            continue
        tickers.append(
            TickerQuote(
                exchange=bitget.EXCHANGE,
                symbol=symbol,
                base=symbol.removesuffix(quote),
                quote=quote,
                bid=to_float(item.get("bidPr")),
                ask=to_float(item.get("askPr")),
                last_price=to_float(item.get("lastPr")),
                mark_price=to_float(item.get("markPrice")),
                funding_rate=to_float(item.get("fundingRate")),
                open_interest=to_float(item.get("holdingAmount")),
                volume_24h=to_float(item.get("baseVolume")),
                quote_volume_24h=to_float(item.get("quoteVolume")) or to_float(item.get("usdtVolume")),
                timestamp_ms=to_int(item.get("ts")),
                raw=item,
            )
        )

    return ExchangeUniverse(
        exchange=bitget.EXCHANGE,
        tickers=tickers,
        latency_ms=round((perf_counter() - started) * 1000, 3),
    )


def fetch_okx_universe(quote: str = "USDT", timeout: float = 10.0) -> ExchangeUniverse:
    started = perf_counter()
    payload, _ = http_get_json(
        okx.BASE_URL,
        "/api/v5/market/tickers",
        {"instType": "SWAP"},
        timeout=timeout,
    )
    ensure(payload.get("code") == "0", "OKX ticker universe request failed", payload)

    tickers: list[TickerQuote] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        inst_id = str(item.get("instId", "")).upper()
        parts = inst_id.split("-")
        if len(parts) != 3 or parts[1] != quote or parts[2] != "SWAP":
            continue

        last_price = to_float(item.get("last"))
        volume_24h = to_float(item.get("volCcy24h"))
        explicit_quote_volume = to_float(item.get("volCcyQuote24h"))
        quote_volume = explicit_quote_volume
        if quote_volume is None and volume_24h is not None and last_price is not None:
            quote_volume = volume_24h * last_price

        tickers.append(
            TickerQuote(
                exchange=okx.EXCHANGE,
                symbol=inst_id,
                base=parts[0],
                quote=quote,
                bid=to_float(item.get("bidPx")),
                ask=to_float(item.get("askPx")),
                last_price=last_price,
                mark_price=None,
                funding_rate=None,
                open_interest=None,
                volume_24h=volume_24h,
                quote_volume_24h=quote_volume,
                timestamp_ms=to_int(item.get("ts")),
                raw=item,
            )
        )

    return ExchangeUniverse(
        exchange=okx.EXCHANGE,
        tickers=tickers,
        latency_ms=round((perf_counter() - started) * 1000, 3),
    )


def fetch_mexc_universe(quote: str = "USDT", timeout: float = 10.0) -> ExchangeUniverse:
    started = perf_counter()
    payload, _ = http_get_json(
        mexc.BASE_URL,
        "/api/v1/contract/ticker",
        timeout=timeout,
    )
    ensure(payload.get("success") is True, "MEXC ticker universe request failed", payload)

    tickers: list[TickerQuote] = []
    suffix = f"_{quote}"
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper()
        if not symbol.endswith(suffix):
            continue
        tickers.append(
            TickerQuote(
                exchange=mexc.EXCHANGE,
                symbol=symbol,
                base=symbol.removesuffix(suffix),
                quote=quote,
                bid=to_float(item.get("bid1")),
                ask=to_float(item.get("ask1")),
                last_price=to_float(item.get("lastPrice")),
                mark_price=to_float(item.get("fairPrice")),
                funding_rate=to_float(item.get("fundingRate")),
                open_interest=to_float(item.get("holdVol")),
                volume_24h=to_float(item.get("volume24")),
                quote_volume_24h=to_float(item.get("amount24")),
                timestamp_ms=to_int(item.get("timestamp")),
                raw=item,
            )
        )

    return ExchangeUniverse(
        exchange=mexc.EXCHANGE,
        tickers=tickers,
        latency_ms=round((perf_counter() - started) * 1000, 3),
    )


def valid_tickers(tickers: list[TickerQuote]) -> list[TickerQuote]:
    return [
        ticker
        for ticker in tickers
        if ticker.bid is not None
        and ticker.ask is not None
        and ticker.bid > 0
        and ticker.ask > 0
        and ticker.quote_volume_24h is not None
        and ticker.quote_volume_24h > 0
    ]


def top_liquid_tickers(tickers: list[TickerQuote], limit: int = 1000) -> list[TickerQuote]:
    by_base: dict[str, TickerQuote] = {}
    for ticker in valid_tickers(tickers):
        previous = by_base.get(ticker.base)
        if previous is None or _quote_volume(ticker) > _quote_volume(previous):
            by_base[ticker.base] = ticker
    return sorted(by_base.values(), key=_quote_volume, reverse=True)[:limit]


def ticker_to_dict(ticker: TickerQuote) -> dict[str, Any]:
    return asdict(ticker)


def _quote_volume(ticker: TickerQuote) -> float:
    return ticker.quote_volume_24h or 0.0


def exchange_names(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_EXCHANGES)
    names = [name.strip().lower() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in DEFAULT_EXCHANGES]
    if unknown:
        raise ValueError(f"Unknown exchanges: {', '.join(unknown)}")
    return names
