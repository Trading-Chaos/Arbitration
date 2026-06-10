# Broker connectors

Низкоуровневый слой подключения к биржам и получения рыночных данных.

## Биржи

- `bybit.py` — Bybit USDT/USDC/inverse futures через V5 market API.
- `bitget.py` — Bitget futures через Mix Market API V2.
- `okx.py` — OKX perpetual swaps через Market/Public Data API V5.
- `mexc.py` — MEXC futures через Contract API V1.

## Единый формат

Каждый модуль возвращает `MarketSnapshot`:

- `bid` / `ask`
- `orderbook`
- `last_price`
- `funding_rate`
- `fees`
- `mark_price`
- `open_interest`
- `volume_24h`
- `latency_ms`
- `raw`

## Быстрый запуск

Из папки проекта:

```bash
python3 -m brokers.bybit BTCUSDT
python3 -m brokers.bitget BTCUSDT
python3 -m brokers.okx BTC-USDT-SWAP
python3 -m brokers.mexc BTC_USDT
```

Форматы символов:

- Bybit: `BTCUSDT`
- Bitget: `BTCUSDT`
- OKX: `BTC-USDT-SWAP`
- MEXC: `BTC_USDT`

Для OKX можно поменять API-домен через `--base-url`, если аккаунт или регион требует отдельный домен.

Логика проверки подключения, выбора top-1000, попарного сравнения spread и периодического мониторинга находится в `src`.
