# Spread scanner and monitor

В `src` лежит логика приложения поверх низкоуровневых коннекторов из `brokers`.

## Проверка подключения

```bash
python3 -m src.connection_check
```

## Разовая попарная сверка spread

```bash
python3 -m src.spread_scanner --limit 50 --csv data/spreads_top1000.csv
```

## Монитор каждые 5 минут

```bash
python3 -m src.spread_monitor
```

По умолчанию монитор:

- проверяет до топ-1000 USDT perpetual на каждой бирже;
- сравнивает одинаковые base symbols между всеми парами бирж;
- считает исполнимый spread: `short_bid / long_ask - 1`;
- печатает в терминал тикер, биржу для long, биржу для short, spread и funding edge;
- по умолчанию выводит spread от `0.5%`;
- повторяет проверку каждые `300` секунд.

Funding edge считается так:

```text
funding_edge_pct = (short_funding_rate - long_funding_rate) * 100
```

Если значение положительное, funding в сторону сделки: long-нога платит меньше/получает больше, short-нога получает больше/платит меньше. Если значение отрицательное, funding против сделки.

Это directional current-rate check, а не полная модель времени удержания. У бирж могут отличаться интервалы funding, а некоторые bulk ticker endpoints не дают funding для всех площадок, поэтому часть строк может быть `unknown`.

Более шумный режим, чтобы вывести любой положительный spread:

```bash
python3 -m src.spread_monitor --min-spread 0 --max-spread 100 --min-volume 0
```

Только сделки, где funding явно в нашу сторону:

```bash
python3 -m src.spread_monitor --require-funding-favorable
```

Разовый тест без ожидания 5 минут:

```bash
python3 -m src.spread_monitor --once
```
