import asyncio
from datetime import timezone

import pytest
from fastapi.testclient import TestClient

from app.api.websocket_routes import manager as websocket_manager
from app.main import app
from app.providers.demo_provider import DemoMarketDataProvider
from app.providers.upstox_provider import UpstoxProvider
from app.services.market_provider import UnconfiguredMarketDataProvider
from app.services.market_service import MarketDataService, market_data_service
import app.services.market_service as market_service_module
from app.websocket.manager import StockSenseWebSocketManager

client = TestClient(app)


def test_demo_provider_initializes_with_synthetic_identity():
    provider = DemoMarketDataProvider()

    assert provider.provider_name == "demo"
    assert provider.data_mode == "demo"
    assert provider.get_quote("TCS").market_status == "DEMO DATA"
    assert "not real-time" in provider.get_market_status().message


def test_demo_stock_lookup_search_quotes_and_invalid_symbol():
    provider = DemoMarketDataProvider()

    quote = provider.get_quote("tcs")
    assert quote.symbol == "TCS"
    assert quote.company_name.startswith("Demo ")
    assert quote.last_price != 0
    assert quote.volume > 0
    assert quote.change_percent == pytest.approx(0.84)
    assert provider.search_symbols("bank")
    assert provider.search_symbols("TCS")[0]["symbol"] == "TCS"
    assert provider.search_symbols("") == []

    with pytest.raises(ValueError, match="Unknown demo stock"):
        provider.get_quote("UNKNOWN")
    with pytest.raises(ValueError, match="symbol must be a string"):
        provider.get_quote(None)


def test_demo_index_quotes_are_explicitly_synthetic():
    index = DemoMarketDataProvider().get_index_quote("NIFTY")

    assert index.symbol == "NIFTY"
    assert index.name.startswith("Demo ")
    assert index.market_status == "DEMO DATA"
    assert index.value > 0


@pytest.mark.parametrize("interval", ["1d", "1w", "1m", "3m", "6m", "1y"])
def test_demo_history_is_deterministic_chronological_and_valid(interval):
    provider = DemoMarketDataProvider()
    first = provider.get_historical_data("TCS", interval)
    second = provider.get_historical_data("TCS", interval)

    assert first == second
    assert first
    assert [candle.timestamp for candle in first] == sorted(candle.timestamp for candle in first)
    for candle in first:
        assert candle.low <= min(candle.open, candle.close)
        assert candle.high >= max(candle.open, candle.close)
        assert candle.volume > 0
        assert candle.timestamp.tzinfo == timezone.utc


def test_demo_movers_and_activity_are_deterministic_and_marked_demo():
    provider = DemoMarketDataProvider()

    assert provider.get_market_movers() == provider.get_market_movers()
    assert provider.get_market_movers()["data_mode"] == "demo"
    assert provider.get_market_movers()["gainers"]
    assert provider.get_market_movers()["losers"]
    activity = provider.get_market_activity()
    assert activity == provider.get_market_activity()
    assert activity["data_mode"] == "demo"
    assert activity["activeStocks"] == 14


def test_provider_configuration_switches_between_demo_and_upstox(monkeypatch):
    monkeypatch.setattr("app.providers.upstox_provider.UPSTOX_ACCESS_TOKEN", "")
    monkeypatch.setattr(market_service_module, "MARKET_DATA_PROVIDER", "demo")
    demo_service = MarketDataService()
    assert isinstance(demo_service.provider, DemoMarketDataProvider)
    assert demo_service.get_quote("TCS").market_status == "DEMO DATA"

    monkeypatch.setattr(market_service_module, "MARKET_DATA_PROVIDER", "upstox")
    monkeypatch.setattr("app.providers.upstox_provider.UPSTOX_ACCESS_TOKEN", "offline-token")
    monkeypatch.setattr("app.providers.instrument_resolver.UPSTOX_INSTRUMENT_MAP", "{}")
    assert isinstance(MarketDataService().provider, UpstoxProvider)

    monkeypatch.setattr(market_service_module, "MARKET_DATA_PROVIDER", "")
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    assert isinstance(MarketDataService().provider, UnconfiguredMarketDataProvider)


def test_demo_market_routes_expose_demo_source_search_movers_and_activity(monkeypatch):
    provider = DemoMarketDataProvider()
    monkeypatch.setattr(websocket_manager, "provider", provider)
    monkeypatch.setattr(market_data_service, "provider", provider)

    status = client.get("/api/system/status").json()
    quote = client.get("/api/market/quote/TCS").json()
    index = client.get("/api/market/index/NIFTY").json()
    search = client.get("/api/market/search?query=bank").json()
    movers = client.get("/api/market/movers").json()
    activity = client.get("/api/market/activity").json()

    assert status["market_data_provider"] == "demo"
    assert status["data_mode"] == "demo"
    assert quote["market_status"] == "DEMO DATA"
    assert index["market_status"] == "DEMO DATA"
    assert search
    assert movers["data_mode"] == "demo"
    assert activity["data_mode"] == "demo"


class RecordingSocket:
    def __init__(self):
        self.messages = []
        self.quote_event = asyncio.Event()

    async def send_json(self, message):
        self.messages.append(message)
        if "symbol" in message:
            self.quote_event.set()


def test_demo_websocket_updates_are_deterministic_filtered_and_cleaned_up():
    async def verify():
        provider = DemoMarketDataProvider(feed_interval_seconds=0.005)
        manager = StockSenseWebSocketManager(provider=provider)
        tcs_client = RecordingSocket()
        infy_client = RecordingSocket()
        await manager.register_client(tcs_client)
        await manager.register_client(infy_client)

        tcs_response = await manager.subscribe(tcs_client, ["TCS"])
        infy_response = await manager.subscribe(infy_client, ["INFY"])
        assert tcs_response["status"] == "demo"
        assert infy_response["status"] == "demo"
        assert "not real-time" in tcs_response["message"]
        assert manager.stream_status == "demo"

        await asyncio.wait_for(
            asyncio.gather(tcs_client.quote_event.wait(), infy_client.quote_event.wait()),
            timeout=1,
        )
        tcs_quotes = [message for message in tcs_client.messages if "symbol" in message]
        infy_quotes = [message for message in infy_client.messages if "symbol" in message]
        assert tcs_quotes and all(message["symbol"] == "TCS" for message in tcs_quotes)
        assert infy_quotes and all(message["symbol"] == "INFY" for message in infy_quotes)
        assert all(message["market_status"] == "DEMO DATA" for message in tcs_quotes + infy_quotes)

        tcs_client.messages.clear()
        tcs_client.quote_event.clear()
        assert await manager.unsubscribe(tcs_client) == {"status": "unsubscribed", "symbols": ["TCS"]}
        await asyncio.wait_for(infy_client.quote_event.wait(), timeout=1)
        assert not [message for message in tcs_client.messages if "symbol" in message]

        await manager.unregister_client(infy_client)
        assert manager._feed_client is None
        assert manager.subscriptions == {}
        await manager.close()

    asyncio.run(verify())


def test_demo_websocket_tick_sequence_repeats_after_restart():
    async def first_tick_price():
        provider = DemoMarketDataProvider(feed_interval_seconds=0.001)
        quote_event = asyncio.Event()
        quotes = []

        async def receive_quote(quote):
            quotes.append(quote)
            quote_event.set()

        feed = provider.create_live_quote_feed_client()
        await feed.start({"TCS": "TCS"}, on_quote=receive_quote)
        await asyncio.wait_for(quote_event.wait(), timeout=0.5)
        first_price = quotes[0].last_price
        await feed.stop()
        return first_price

    assert asyncio.run(first_tick_price()) == asyncio.run(first_tick_price())


def test_browser_websocket_route_uses_demo_status_and_normalized_quotes(monkeypatch):
    provider = DemoMarketDataProvider(feed_interval_seconds=0.001)
    monkeypatch.setattr(websocket_manager, "provider", provider)

    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["TCS"]})
        responses = [websocket.receive_json() for _ in range(3)]

    demo_statuses = [response for response in responses if response.get("status") == "demo"]
    quote_updates = [response for response in responses if response.get("symbol") == "TCS"]
    assert demo_statuses
    assert all("not real-time" in response["message"] for response in demo_statuses)
    assert quote_updates
    assert quote_updates[0]["market_status"] == "DEMO DATA"
    assert "instrument_key" not in quote_updates[0]