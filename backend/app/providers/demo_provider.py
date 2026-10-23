from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Sequence

from app.schemas.market import HistoricalCandle, IndexQuote, MarketQuote, MarketStatus
from app.services.market_provider import MarketDataProvider

DEMO_AS_OF = datetime(2025, 1, 1, 15, 30, tzinfo=timezone.utc)
DEMO_DISCLAIMER = "Demo/synthetic market data — not real-time market data"
PRICE_OFFSETS_BPS = (0, 4, 9, 5, -2, -7, -3, 3, 8, 2, -5, -9, -1, 6, 1, -4)


@dataclass(frozen=True)
class DemoInstrument:
    company_name: str
    exchange: str
    base_price: float
    daily_change_percent: float
    base_volume: int
    seed: int


DEMO_STOCKS = {
    "TCS": DemoInstrument("Demo Technology One", "NSE", 1843.27, 0.84, 842_600, 11),
    "INFY": DemoInstrument("Demo Technology Two", "NSE", 1217.83, -0.42, 726_400, 17),
    "RELIANCE": DemoInstrument("Demo Consumer Group", "NSE", 2631.49, 1.15, 1_258_000, 23),
    "HDFCBANK": DemoInstrument("Demo Bank One", "NSE", 1688.21, -0.28, 913_700, 29),
    "ICICIBANK": DemoInstrument("Demo Bank Two", "NSE", 1142.36, 0.53, 778_900, 31),
    "SBIN": DemoInstrument("Demo Bank Three", "NSE", 742.83, 1.62, 1_031_500, 37),
    "ITC": DemoInstrument("Demo Consumer Two", "NSE", 431.26, -0.71, 652_100, 41),
    "LT": DemoInstrument("Demo Infrastructure Group", "NSE", 3584.31, 0.94, 489_300, 43),
    "WIPRO": DemoInstrument("Demo Technology Three", "NSE", 523.17, -1.04, 574_800, 47),
    "BHARTIARTL": DemoInstrument("Demo Communications Group", "NSE", 1518.46, 0.37, 691_200, 53),
    "MARUTI": DemoInstrument("Demo Mobility Group", "NSE", 11276.24, -0.33, 231_700, 59),
    "TATAMOTORS": DemoInstrument("Demo Mobility Two", "NSE", 964.82, 1.28, 822_900, 61),
    "AXISBANK": DemoInstrument("Demo Bank Four", "NSE", 1185.34, -0.16, 602_400, 67),
    "SUNPHARMA": DemoInstrument("Demo Healthcare Group", "NSE", 1674.92, 0.60, 381_600, 71),
}

DEMO_INDEXES = {
    "NIFTY": ("Demo Broad Market Index", 18432.75, 0.43),
    "BANKNIFTY": ("Demo Banking Index", 42186.35, -0.31),
    "SENSEX": ("Demo Composite Index", 61248.90, 0.26),
    "INDIAVIX": ("Demo Volatility Index", 16.42, -0.88),
}

_HISTORY_LENGTHS = {"1d": 24, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic synthetic market data for local demos, never provider data."""

    provider_name = "demo"
    data_mode = "demo"
    streaming_available = True

    def __init__(self, *, feed_interval_seconds: float = 1.0):
        self.feed_interval_seconds = max(0.001, feed_interval_seconds)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("symbol must be a string")
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    def _instrument(self, symbol: str) -> DemoInstrument:
        normalized = self._normalize_symbol(symbol)
        instrument = DEMO_STOCKS.get(normalized)
        if instrument is None:
            raise ValueError(f"Unknown demo stock symbol: {normalized}")
        return instrument

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized = self._normalize_symbol(symbol)
        instrument = self._instrument(normalized)
        previous_close = instrument.base_price
        last_price = previous_close * (1 + instrument.daily_change_percent / 100)
        open_price = previous_close * (1 + instrument.daily_change_percent / 400)
        high = max(open_price, last_price, previous_close) * 1.004
        low = min(open_price, last_price, previous_close) * 0.996
        volume = instrument.base_volume + instrument.seed * 97
        return MarketQuote(
            symbol=normalized,
            exchange=instrument.exchange,
            company_name=instrument.company_name,
            last_price=round(last_price, 2),
            previous_close=round(previous_close, 2),
            change=round(last_price - previous_close, 2),
            change_percent=instrument.daily_change_percent,
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            volume=volume,
            timestamp=DEMO_AS_OF,
            market_status="DEMO DATA",
        )

    def get_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        return [self.get_quote(symbol) for symbol in symbols]

    def search_symbols(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        normalized_query = query.strip().upper()
        if not normalized_query:
            return []
        matches = [
            {"symbol": symbol, "company_name": instrument.company_name, "exchange": instrument.exchange}
            for symbol, instrument in DEMO_STOCKS.items()
            if normalized_query in symbol or normalized_query in instrument.company_name.upper()
        ]
        return matches[: max(0, min(limit, 20))]

    def get_historical_data(self, symbol: str, interval: str = "1d") -> list[HistoricalCandle]:
        normalized = self._normalize_symbol(symbol)
        instrument = self._instrument(normalized)
        normalized_interval = interval.strip().lower()
        candle_count = _HISTORY_LENGTHS.get(normalized_interval)
        if candle_count is None:
            raise ValueError("interval must be one of 1d, 1w, 1m, 3m, 6m, or 1y")

        start_timestamp = DEMO_AS_OF - (
            timedelta(hours=candle_count - 1)
            if normalized_interval == "1d"
            else timedelta(days=candle_count - 1)
        )
        candles = []
        previous_close = instrument.base_price * 0.965
        for index in range(candle_count):
            variation_bps = ((index * 37 + instrument.seed * 13) % 161) - 80
            open_price = previous_close * (1 + variation_bps / 10_000)
            move_bps = ((index * 29 + instrument.seed * 7) % 51) - 25
            close_price = open_price * (1 + move_bps / 10_000)
            spread_bps = 5 + ((index + instrument.seed) % 12)
            high = max(open_price, close_price) * (1 + spread_bps / 10_000)
            low = min(open_price, close_price) * (1 - spread_bps / 10_000)
            volume = int(instrument.base_volume * (0.65 + ((index * 19 + instrument.seed * 11) % 71) / 100))
            timestamp = start_timestamp + (
                timedelta(hours=index) if normalized_interval == "1d" else timedelta(days=index)
            )
            candles.append(
                HistoricalCandle(
                    symbol=normalized,
                    timestamp=timestamp,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close_price, 2),
                    volume=volume,
                )
            )
            previous_close = close_price
        return candles

    def get_index_quote(self, symbol: str) -> IndexQuote:
        normalized = self._normalize_symbol(symbol)
        index = DEMO_INDEXES.get(normalized)
        if index is None:
            raise ValueError(f"Unknown demo index symbol: {normalized}")
        name, previous_close, change_percent = index
        value = previous_close * (1 + change_percent / 100)
        return IndexQuote(
            symbol=normalized,
            exchange="NSE" if normalized != "SENSEX" else "BSE",
            name=name,
            value=round(value, 2),
            previous_close=previous_close,
            change=round(value - previous_close, 2),
            change_percent=change_percent,
            timestamp=DEMO_AS_OF,
            market_status="DEMO DATA",
        )

    def get_market_status(self, exchange: str = "NSE") -> MarketStatus:
        return MarketStatus(
            exchange=exchange.strip().upper(),
            market_status="DEMO DATA",
            timestamp=DEMO_AS_OF,
            message=DEMO_DISCLAIMER,
            is_open=False,
        )

    def get_market_movers(self) -> dict:
        quotes = self.get_quotes(list(DEMO_STOCKS))
        ordered = sorted(quotes, key=lambda quote: quote.change_percent or 0)
        return {
            "gainers": [
                {"symbol": quote.symbol, "change": f"{quote.change_percent:+.2f}%", "change_percent": quote.change_percent}
                for quote in reversed(ordered[-4:])
            ],
            "losers": [
                {"symbol": quote.symbol, "change": f"{quote.change_percent:+.2f}%", "change_percent": quote.change_percent}
                for quote in ordered[:4]
            ],
            "data_mode": "demo",
        }

    def get_market_activity(self) -> dict[str, int | str]:
        quotes = self.get_quotes(list(DEMO_STOCKS))
        advancing = sum((quote.change_percent or 0) > 0 for quote in quotes)
        declining = sum((quote.change_percent or 0) < 0 for quote in quotes)
        return {
            "volume": sum(quote.volume or 0 for quote in quotes),
            "activeStocks": len(quotes),
            "advancing": advancing,
            "declining": declining,
            "data_mode": "demo",
        }

    def subscribe_live_quotes(self, symbols: Sequence[str]):
        symbol_to_key = self.resolve_live_quote_symbols(symbols)
        return {"provider": self.provider_name, "subscription_symbols": list(symbol_to_key.values()), "status": "demo"}

    def resolve_live_quote_symbols(self, symbols: Sequence[str]) -> dict[str, str]:
        if not isinstance(symbols, Sequence) or isinstance(symbols, (str, bytes)) or not symbols:
            raise ValueError("symbols must be a non-empty list without duplicates")
        keys = []
        for symbol in symbols:
            self._instrument(symbol)
            keys.append(symbol.strip().upper())
        if len(set(keys)) != len(keys):
            raise ValueError("symbols must be a non-empty list without duplicates")
        return dict(zip(keys, keys))

    def create_live_quote_feed_client(self):
        return DemoQuoteFeedClient(self, interval_seconds=self.feed_interval_seconds)


class DemoQuoteFeedClient:
    def __init__(self, provider: DemoMarketDataProvider, *, interval_seconds: float = 1.0):
        self.provider = provider
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._symbols: dict[str, str] = {}
        self._on_quote: Callable[[MarketQuote], Awaitable[None] | None] | None = None
        self._on_status: Callable[[str], Awaitable[None] | None] | None = None
        self._tick = 0

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _emit(self, callback, value) -> None:
        if callback is None:
            return
        result = callback(value)
        if asyncio.iscoroutine(result):
            await result

    async def start(self, symbol_to_key, *, on_quote, on_status=None) -> None:
        if not symbol_to_key:
            raise ValueError("at least one demo symbol is required")
        if self.is_running:
            raise RuntimeError("demo quote feed is already running")
        self._symbols = dict(symbol_to_key)
        self._on_quote = on_quote
        self._on_status = on_status
        self._tick = 0
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        await self._emit(self._on_status, "demo_connected")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
                return
            except asyncio.TimeoutError:
                pass

            offset_bps = PRICE_OFFSETS_BPS[self._tick % len(PRICE_OFFSETS_BPS)]
            timestamp = DEMO_AS_OF + timedelta(seconds=self._tick + 1)
            for symbol in self._symbols:
                quote = self.provider.get_quote(symbol)
                base = DEMO_STOCKS[symbol].base_price
                last_price = round(base * (1 + offset_bps / 10_000), 2)
                previous_close = quote.previous_close or base
                quote.last_price = last_price
                quote.change = round(last_price - previous_close, 2)
                quote.change_percent = round((last_price / previous_close - 1) * 100, 4)
                quote.timestamp = timestamp
                quote.market_status = "DEMO DATA"
                await self._emit(self._on_quote, quote)
            self._tick += 1

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._symbols = {}
        self._on_quote = None
        self._on_status = None