from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from app.schemas.market import HistoricalCandle, IndexQuote, MarketQuote, MarketStatus


class ProviderConfigurationError(RuntimeError):
    """Raised when the market data provider is not configured."""


class MarketDataProvider(ABC):
    """Abstract contract for a real market-data provider adapter."""

    provider_name = "provider"
    data_mode = "provider"
    streaming_available = False

    @abstractmethod
    def get_quote(self, symbol: str) -> MarketQuote:
        """Return a quote for a single symbol."""

    @abstractmethod
    def get_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        """Return quotes for multiple symbols."""

    @abstractmethod
    def get_historical_data(self, symbol: str, interval: str = "1d") -> list[HistoricalCandle]:
        """Return historical OHLCV candles."""

    @abstractmethod
    def get_index_quote(self, symbol: str) -> IndexQuote:
        """Return an index quote."""

    @abstractmethod
    def get_market_status(self, exchange: str = "NSE") -> MarketStatus:
        """Return market status for an exchange."""

    @abstractmethod
    def subscribe_live_quotes(self, symbols: Sequence[str]):
        """Validate and prepare a provider subscription request."""

    def resolve_live_quote_symbols(self, symbols: Sequence[str]) -> dict[str, str]:
        """Map normalized application symbols to provider instrument keys."""
        raise ProviderConfigurationError("Live market-data streaming is not available for this provider.")

    def create_live_quote_feed_client(self):
        """Create a provider-owned client for upstream streaming."""
        raise ProviderConfigurationError("Live market-data streaming is not available for this provider.")

    def search_symbols(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        return []

    def get_market_movers(self) -> dict:
        raise ProviderConfigurationError("Market movers are not available for this provider.")

    def get_market_activity(self) -> dict:
        raise ProviderConfigurationError("Market activity is not available for this provider.")


class UnconfiguredMarketDataProvider(MarketDataProvider):
    """Temporary provider implementation used before credentials are configured."""

    provider_name = "unconfigured"
    data_mode = "unavailable"

    def __init__(self, message: str | None = None):
        self.message = message or (
            "Market data provider is not configured. Set MARKET_DATA_PROVIDER and related credentials "
            "in the backend .env file before enabling live market data."
        )

    def _raise_configuration_error(self) -> None:
        raise ProviderConfigurationError(self.message)

    def get_quote(self, symbol: str) -> MarketQuote:
        self._raise_configuration_error()

    def get_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        self._raise_configuration_error()

    def get_historical_data(self, symbol: str, interval: str = "1d") -> list[HistoricalCandle]:
        self._raise_configuration_error()

    def get_index_quote(self, symbol: str) -> IndexQuote:
        self._raise_configuration_error()

    def get_market_status(self, exchange: str = "NSE") -> MarketStatus:
        self._raise_configuration_error()

    def subscribe_live_quotes(self, symbols: Sequence[str]):
        self._raise_configuration_error()
