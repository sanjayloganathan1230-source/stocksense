from app.services.market_provider import (
    MarketDataProvider,
    ProviderConfigurationError,
    UnconfiguredMarketDataProvider,
)


def __getattr__(name):
    if name == "market_data_service":
        from app.services.market_service import market_data_service

        return market_data_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "MarketDataProvider",
    "ProviderConfigurationError",
    "UnconfiguredMarketDataProvider",
    "market_data_service",
]
