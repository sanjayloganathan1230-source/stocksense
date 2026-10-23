from __future__ import annotations

import os
from typing import Sequence

from app.config import MARKET_DATA_PROVIDER
from app.providers.demo_provider import DemoMarketDataProvider
from app.providers.upstox_provider import UpstoxProvider
from app.schemas.market import HistoricalCandle, IndexQuote, MarketQuote, MarketStatus
from app.services.market_provider import MarketDataProvider, ProviderConfigurationError, UnconfiguredMarketDataProvider


class MarketDataService:
    """Service layer that isolates the rest of the app from any one provider."""

    def __init__(self, provider: MarketDataProvider | None = None):
        self.provider = provider or self._build_provider()

    @staticmethod
    def _build_provider() -> MarketDataProvider:
        provider_name = (MARKET_DATA_PROVIDER or os.getenv("MARKET_DATA_PROVIDER", "")).strip().lower()

        if provider_name == "demo":
            return DemoMarketDataProvider()

        if provider_name == "upstox":
            try:
                return UpstoxProvider()
            except ProviderConfigurationError as exc:
                return UnconfiguredMarketDataProvider(str(exc))

        if not provider_name:
            return UnconfiguredMarketDataProvider()

        return UnconfiguredMarketDataProvider(
            f"Unsupported market data provider '{provider_name}'. Configure a supported provider."
        )

    def normalize_symbol(self, symbol: str) -> str:
        cleaned = symbol.strip().upper()
        if not cleaned:
            raise ValueError("symbol is required")
        if not cleaned.replace("-", "").replace(".", "").isalnum():
            raise ValueError("symbol contains unsupported characters")
        return cleaned

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized_symbol = self.normalize_symbol(symbol)
        return self.provider.get_quote(normalized_symbol)

    def get_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        normalized_symbols = [self.normalize_symbol(symbol) for symbol in symbols]
        return self.provider.get_quotes(normalized_symbols)

    def get_historical_data(self, symbol: str, interval: str = "1d") -> list[HistoricalCandle]:
        normalized_symbol = self.normalize_symbol(symbol)
        return self.provider.get_historical_data(normalized_symbol, interval)

    def get_index_quote(self, symbol: str) -> IndexQuote:
        normalized_symbol = self.normalize_symbol(symbol)
        return self.provider.get_index_quote(normalized_symbol)

    def get_market_status(self, exchange: str = "NSE") -> MarketStatus:
        return self.provider.get_market_status(exchange)

    def subscribe_live_quotes(self, symbols: Sequence[str]):
        normalized_symbols = [self.normalize_symbol(symbol) for symbol in symbols]
        return self.provider.subscribe_live_quotes(normalized_symbols)

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    @property
    def data_mode(self) -> str:
        return self.provider.data_mode

    def search_symbols(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        return self.provider.search_symbols(query, limit)

    def get_market_movers(self) -> dict:
        return self.provider.get_market_movers()

    def get_market_activity(self) -> dict:
        return self.provider.get_market_activity()


market_data_service = MarketDataService()
