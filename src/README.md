# Spread scanner and monitor

В `src` лежит логика приложения поверх низкоуровневых коннекторов из `brokers`.

## Проверка подключения

```bash
python -m src.connection_check
```

## Разовая попарная сверка spread

```bash
python -m src.spread_scanner --top 300 --limit 50 --csv data/spreads_top300.csv
```

## Монитор каждые 5 минут

```bash
python -m src.spread_monitor
```

По умолчанию монитор:

- проверяет топ-300 USDT perpetual на каждой бирже;
- сравнивает одинаковые base symbols между всеми парами бирж;
- считает исполнимый spread: `short_bid / long_ask - 1`;
- печатает в терминал тикер, биржу для long, биржу для short и размер spread;
- повторяет проверку каждые `300` секунд.

Более шумный режим, чтобы вывести любой положительный spread:

```bash
python -m src.spread_monitor --min-spread 0 --max-spread 100 --min-volume 0
```

Разовый тест без ожидания 5 минут:

```bash
python -m src.spread_monitor --once
```
