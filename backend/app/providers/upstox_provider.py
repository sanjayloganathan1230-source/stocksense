from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence
from urllib.parse import quote

import httpx

from app.config import MARKET_DATA_BASE_URL, UPSTOX_ACCESS_TOKEN
from app.providers.instrument_resolver import InstrumentResolver
from app.providers.upstox_feed import UpstoxFeedAuthorizer, UpstoxV3FeedClient
from app.schemas.market import HistoricalCandle, IndexQuote, MarketQuote, MarketStatus
from app.services.market_provider import MarketDataProvider, ProviderConfigurationError


class UpstoxProvider(MarketDataProvider):
    """Concrete adapter for the Upstox v3 market-data APIs."""

    provider_name = "upstox"
    data_mode = "provider"
    streaming_available = True

    _HISTORY_WINDOWS_DAYS = {
        "1d": 1,
        "1w": 7,
        "1m": 30,
        "3m": 90,
        "6m": 180,
        "1y": 365,
    }

    def __init__(
        self,
        *,
        access_token: str | None = None,
        base_url: str | None = None,
        instrument_map: str | dict[str, str] | None = None,
        feed_authorizer: UpstoxFeedAuthorizer | None = None,
        websocket_connect=None,
    ):
        self.base_url = (base_url or MARKET_DATA_BASE_URL).rstrip("/")
        self.access_token = UPSTOX_ACCESS_TOKEN if access_token is None else access_token

        if not self.access_token:
            raise ProviderConfigurationError(
                "Upstox is not configured. Set UPSTOX_ACCESS_TOKEN in the project .env file."
            )
        self.instrument_resolver = InstrumentResolver(instrument_map)
        self.feed_authorizer = feed_authorizer or UpstoxFeedAuthorizer(
            access_token=self.access_token,
            base_url=self.base_url,
        )
        self.websocket_connect = websocket_connect

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def _validate_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str):
            raise ValueError("symbol must be a string")
        cleaned = symbol.strip().upper()
        if not cleaned:
            raise ValueError("symbol is required")
        if not cleaned.replace("-", "").replace(".", "").isalnum():
            raise ValueError("symbol contains unsupported characters")
        return cleaned

    def _resolve_instrument_key(self, symbol: str) -> str:
        normalized = self._validate_symbol(symbol)
        instrument_key = self.instrument_resolver.resolve_symbol(normalized)
        if "|" not in instrument_key:
            raise ProviderConfigurationError(
                f"No Upstox instrument key is configured for {normalized}. Add it to UPSTOX_INSTRUMENT_MAP."
            )
        return instrument_key

    def _request_json(self, url: str, *, context: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = httpx.get(url, headers=self._headers(), params=params, timeout=20)
        except httpx.HTTPError as exc:
            raise ProviderConfigurationError(f"Upstox request failed while fetching {context}.") from exc

        status_code = response.status_code
        if status_code in (401, 403):
            raise ProviderConfigurationError(f"Upstox authentication failed while fetching {context}.")
        if status_code == 404:
            raise ProviderConfigurationError(f"Upstox instrument or endpoint was not found while fetching {context}.")
        if status_code == 429:
            raise ProviderConfigurationError(f"Upstox rate limit reached while fetching {context}.")
        if status_code >= 500:
            raise ProviderConfigurationError(f"Upstox provider unavailable while fetching {context}.")
        if status_code >= 400:
            raise ProviderConfigurationError(f"Upstox rejected the request for {context} (HTTP {status_code}).")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderConfigurationError(f"Upstox returned malformed JSON while fetching {context}.") from exc
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise ProviderConfigurationError(f"Upstox returned an invalid response while fetching {context}.")
        return payload

    @staticmethod
    def _number(value: Any, *, field: str) -> float:
        if isinstance(value, bool):
            raise ProviderConfigurationError(f"Upstox response contains an invalid {field} value.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ProviderConfigurationError(f"Upstox response is missing a valid {field} value.") from exc
        if not math.isfinite(number):
            raise ProviderConfigurationError(f"Upstox response contains an invalid {field} value.")
        return number

    @classmethod
    def _optional_number(cls, payload: dict[str, Any], field: str, *, context: str) -> float | None:
        value = payload.get(field)
        if value is None:
            return None
        return cls._number(value, field=f"{context}.{field}")

    @classmethod
    def _volume(cls, value: Any, *, field: str) -> int:
        number = cls._number(value, field=field)
        if not number.is_integer() or number < 0:
            raise ProviderConfigurationError(f"Upstox response contains an invalid {field} value.")
        return int(number)

    @staticmethod
    def _timestamp(value: Any, *, field: str) -> datetime | None:
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (OverflowError, OSError, TypeError, ValueError) as exc:
            raise ProviderConfigurationError(f"Upstox response contains an invalid {field} value.") from exc
        raise ProviderConfigurationError(f"Upstox response contains an invalid {field} value.")

    def _quote_record(self, payload: dict[str, Any], instrument_key: str, *, context: str) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict) or not data:
            raise ProviderConfigurationError(f"Upstox returned no {context} data for {instrument_key}.")

        records = [record for record in data.values() if isinstance(record, dict)]
        for record in records:
            if record.get("instrument_token") == instrument_key:
                return record
        raise ProviderConfigurationError(f"Upstox returned no valid {context} data for {instrument_key}.")

    def _get_ohlc_record(self, symbol: str) -> tuple[str, str, dict[str, Any]]:
        normalized_symbol = self._validate_symbol(symbol)
        instrument_key = self._resolve_instrument_key(normalized_symbol)
        payload = self._request_json(
            f"{self.base_url}/v3/market-quote/ohlc",
            context=f"quote for {instrument_key}",
            params={"instrument_key": instrument_key, "interval": "1d"},
        )
        record = self._quote_record(payload, instrument_key, context="quote")
        if "last_price" not in record:
            raise ProviderConfigurationError(f"Upstox quote for {instrument_key} is missing last_price.")
        return normalized_symbol, instrument_key, record

    @staticmethod
    def _exchange(instrument_key: str) -> str:
        return instrument_key.split("_", 1)[0]

    def _normalize_quote_values(self, record: dict[str, Any]) -> dict[str, Any]:
        last_price = self._number(record["last_price"], field="last_price")
        previous = record.get("prev_ohlc", {})
        live = record.get("live_ohlc", {})
        previous = {} if previous is None else previous
        live = {} if live is None else live
        if not isinstance(previous, dict) or not isinstance(live, dict):
            raise ProviderConfigurationError("Upstox quote contains malformed OHLC data.")

        previous_close = self._optional_number(previous, "close", context="prev_ohlc")
        change = last_price - previous_close if previous_close is not None else None
        change_percent = (
            change / previous_close * 100
            if change is not None and previous_close not in (None, 0)
            else None
        )
        candle = live or previous
        volume_value = candle.get("volume")
        timestamp = self._timestamp(candle.get("ts"), field="ohlc.ts")
        return {
            "last_price": last_price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
            "open": self._optional_number(candle, "open", context="ohlc"),
            "high": self._optional_number(candle, "high", context="ohlc"),
            "low": self._optional_number(candle, "low", context="ohlc"),
            "volume": self._volume(volume_value, field="ohlc.volume") if volume_value is not None else None,
            "timestamp": timestamp,
            "market_status": None,
        }

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized_symbol, instrument_key, record = self._get_ohlc_record(symbol)
        return MarketQuote(
            symbol=normalized_symbol,
            exchange=self._exchange(instrument_key),
            **self._normalize_quote_values(record),
        )

    def get_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        return [self.get_quote(symbol) for symbol in symbols]

    def get_historical_data(self, symbol: str, interval: str = "1d") -> list[HistoricalCandle]:
        normalized_symbol = self._validate_symbol(symbol)
        instrument_key = self._resolve_instrument_key(normalized_symbol)
        lookback_days = self._HISTORY_WINDOWS_DAYS.get(interval.lower())
        if lookback_days is None:
            raise ValueError("interval must be one of 1d, 1w, 1m, 3m, 6m, or 1y")

        to_date = date.today()
        from_date = to_date - timedelta(days=lookback_days - 1)
        encoded_key = quote(instrument_key, safe="")
        url = (
            f"{self.base_url}/v3/historical-candle/{encoded_key}/days/1/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )
        payload = self._request_json(url, context=f"historical data for {instrument_key}")
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("candles"), list):
            raise ProviderConfigurationError("Upstox historical response is missing a valid candles list.")

        candles = []
        for index, item in enumerate(data["candles"]):
            if not isinstance(item, list) or len(item) < 6:
                raise ProviderConfigurationError(f"Upstox candle {index} has an invalid structure.")
            timestamp = self._timestamp(item[0], field=f"candles[{index}].timestamp")
            if timestamp is None:
                raise ProviderConfigurationError(f"Upstox candle {index} is missing a timestamp.")
            candles.append(
                HistoricalCandle(
                    symbol=normalized_symbol,
                    timestamp=timestamp,
                    open=self._number(item[1], field=f"candles[{index}].open"),
                    high=self._number(item[2], field=f"candles[{index}].high"),
                    low=self._number(item[3], field=f"candles[{index}].low"),
                    close=self._number(item[4], field=f"candles[{index}].close"),
                    volume=self._volume(item[5], field=f"candles[{index}].volume"),
                )
            )
        return candles

    def get_index_quote(self, symbol: str) -> IndexQuote:
        normalized_symbol, instrument_key, record = self._get_ohlc_record(symbol)
        values = self._normalize_quote_values(record)
        return IndexQuote(
            symbol=normalized_symbol,
            exchange=self._exchange(instrument_key),
            name=normalized_symbol,
            value=values["last_price"],
            previous_close=values["previous_close"],
            change=values["change"],
            change_percent=values["change_percent"],
            timestamp=values["timestamp"],
            market_status=values["market_status"],
        )

    def get_market_status(self, exchange: str = "NSE") -> MarketStatus:
        return MarketStatus(
            exchange=exchange,
            market_status="UNAVAILABLE",
            timestamp=None,
            message="Upstox market status is not available through the current REST adapter.",
            is_open=False,
        )

    def search_symbols(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        normalized_query = query.strip().upper()
        if not normalized_query:
            return []
        return [
            {"symbol": symbol, "company_name": symbol, "exchange": key.split("_", 1)[0]}
            for symbol, key in self.instrument_resolver.get_mapping().items()
            if normalized_query in symbol
        ][: max(0, min(limit, 20))]

    def subscribe_live_quotes(self, symbols: Sequence[str]):
        symbol_to_key = self.resolve_live_quote_symbols(symbols)
        return {
            "provider": "upstox",
            "subscription_symbols": list(symbol_to_key.values()),
            "status": "prepared",
        }

    def resolve_live_quote_symbols(self, symbols: Sequence[str]) -> dict[str, str]:
        if not isinstance(symbols, Sequence) or isinstance(symbols, (str, bytes)) or not symbols:
            raise ValueError("symbols must be a non-empty sequence")

        symbol_to_key: dict[str, str] = {}
        for symbol in symbols:
            normalized = self._validate_symbol(symbol)
            if normalized in symbol_to_key:
                raise ValueError("symbols must not contain duplicates")
            symbol_to_key[normalized] = self._resolve_instrument_key(normalized)

        if len(set(symbol_to_key.values())) != len(symbol_to_key):
            raise ProviderConfigurationError("UPSTOX_INSTRUMENT_MAP must map symbols to unique instrument keys.")
        return symbol_to_key

    def create_live_quote_feed_client(self) -> UpstoxV3FeedClient:
        options = {}
        if self.websocket_connect is not None:
            options["websocket_connect"] = self.websocket_connect
        return UpstoxV3FeedClient(self.feed_authorizer, **options)
