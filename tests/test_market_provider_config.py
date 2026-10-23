import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.market_provider import ProviderConfigurationError, UnconfiguredMarketDataProvider
from app.services.market_service import MarketDataService, market_data_service
from app.api.websocket_routes import manager as websocket_manager
import app.services.market_service as market_service_module

client = TestClient(app)


class AcceptingSubscriptionProvider:
    def __init__(self):
        self.calls = []

    def subscribe_live_quotes(self, symbols):
        self.calls.append(list(symbols))
        return {"status": "subscribed"}


class RaisingSubscriptionProvider:
    def subscribe_live_quotes(self, symbols):
        raise RuntimeError("private provider diagnostic")


class EmptySubscriptionProvider:
    def subscribe_live_quotes(self, symbols):
        return None


class ConfigurationErrorSubscriptionProvider:
    def subscribe_live_quotes(self, symbols):
        raise ProviderConfigurationError("Instrument mapping is unavailable.")


def test_market_data_service_reports_missing_access_token(monkeypatch):
    monkeypatch.setattr(market_service_module, "MARKET_DATA_PROVIDER", "upstox")
    monkeypatch.setattr("app.providers.upstox_provider.UPSTOX_ACCESS_TOKEN", "")
    service = MarketDataService()

    with pytest.raises(ProviderConfigurationError, match="UPSTOX_ACCESS_TOKEN"):
        service.get_quote("TCS")


def test_market_data_service_preserves_invalid_mapping_error(monkeypatch):
    monkeypatch.setattr(market_service_module, "MARKET_DATA_PROVIDER", "upstox")
    monkeypatch.setattr("app.providers.upstox_provider.UPSTOX_ACCESS_TOKEN", "offline-token")
    monkeypatch.setattr("app.providers.instrument_resolver.UPSTOX_INSTRUMENT_MAP", "{invalid")
    service = MarketDataService()

    with pytest.raises(ProviderConfigurationError, match="valid JSON object"):
        service.get_quote("TCS")


def test_market_data_service_reports_unsupported_provider(monkeypatch):
    monkeypatch.setattr(market_service_module, "MARKET_DATA_PROVIDER", "")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "unknown-provider")
    service = MarketDataService()

    with pytest.raises(ProviderConfigurationError, match="Unsupported market data provider"):
        service.get_quote("TCS")


def test_quote_endpoint_validation_error_for_empty_symbol():
    response = client.get('/api/market/quote/   ')
    assert response.status_code == 400


def test_quote_endpoint_returns_provider_error_when_unconfigured(monkeypatch):
    monkeypatch.setattr(market_data_service, "provider", UnconfiguredMarketDataProvider())
    response = client.get('/api/market/quote/TCS')
    assert response.status_code == 503
    assert 'not configured' in response.json()['detail'].lower()


def test_invalid_symbol_rejected_by_service():
    service = MarketDataService()

    with pytest.raises(ValueError):
        service.normalize_symbol('!!!')


@pytest.mark.parametrize(
    "path",
    [
        "/api/market/status",
        "/api/market/quote/TCS",
        "/api/market/index/NIFTY",
        "/api/market/historical/TCS",
    ],
)
def test_market_endpoints_fail_safely_without_provider(path, monkeypatch):
    monkeypatch.setattr(market_data_service, "provider", UnconfiguredMarketDataProvider())

    response = client.get(path)

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_websocket_does_not_acknowledge_a_missing_stream(monkeypatch):
    monkeypatch.setattr(websocket_manager, "provider", None)

    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["TCS"]})
        response = websocket.receive_json()

    assert response["status"] == "unavailable"
    assert "not configured" in response["message"]


@pytest.mark.parametrize(
    "symbols",
    [["A" * 21], ["ＴＣＳ"], ["TCS"] * 51],
)
def test_websocket_rejects_invalid_subscription_symbols(symbols):
    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": symbols})
        response = websocket.receive_json()

    assert response["status"] == "error"
    assert response["error"]["code"] == "invalid_symbols"
    assert websocket_manager.subscriptions == {}


@pytest.mark.parametrize(
    ("provider", "expected_message"),
    [
        (EmptySubscriptionProvider(), "not available"),
        (ConfigurationErrorSubscriptionProvider(), "Instrument mapping is unavailable."),
    ],
)
def test_websocket_does_not_acknowledge_invalid_provider_subscriptions(
    monkeypatch, provider, expected_message
):
    monkeypatch.setattr(websocket_manager, "provider", provider)

    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["TCS"]})
        response = websocket.receive_json()

    assert response["status"] == "unavailable"
    assert expected_message in response["message"]
    assert websocket_manager.subscriptions == {}


@pytest.mark.parametrize(
    ("raw_message", "error_code"),
    [
        ("", "empty_message"),
        ("not json", "malformed_json"),
        (" " * 8193, "message_too_large"),
        ("[]", "invalid_message"),
        ('"text"', "invalid_message"),
        ("42", "invalid_message"),
        ("{}", "missing_action"),
        ('{"action": 1}', "missing_action"),
        ('{"action": "unknown"}', "unknown_action"),
        ('{"action": "subscribe"}', "missing_symbols"),
        ('{"action": "subscribe", "symbols": "TCS"}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": []}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": [""]}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": ["NSE_EQ|KEY"]}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": [2]}', "invalid_symbols"),
        ('{"action": "unsubscribe", "symbols": []}', "invalid_symbols"),
    ],
)
def test_invalid_websocket_messages_return_structured_errors(raw_message, error_code):
    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_text(raw_message)
        response = websocket.receive_json()

        assert response["status"] == "error"
        assert response["error"]["code"] == error_code
        assert isinstance(response["error"]["message"], str)

        websocket.send_json({"action": "unsupported"})
        assert websocket.receive_json()["error"]["code"] == "unknown_action"

    assert websocket_manager.clients == set()
    assert websocket_manager.subscriptions == {}


def test_binary_websocket_message_returns_error_and_keeps_connection_open():
    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_bytes(b"not text")
        response = websocket.receive_json()

        assert response == {
            "status": "error",
            "error": {"code": "invalid_message", "message": "Message must be text."},
        }

        websocket.send_json({"action": "unsupported"})
        assert websocket.receive_json()["error"]["code"] == "unknown_action"

    assert websocket_manager.clients == set()
    assert websocket_manager.subscriptions == {}


def test_duplicate_websocket_subscribe_is_idempotent(monkeypatch):
    provider = AcceptingSubscriptionProvider()
    monkeypatch.setattr(websocket_manager, "provider", provider)

    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": [" tcs ", "TCS"]})
        first = websocket.receive_json()
        websocket.send_json({"action": "subscribe", "symbols": ["TCS"]})
        duplicate = websocket.receive_json()

        assert first == {"status": "subscribed", "symbols": ["TCS"]}
        assert duplicate == first
        assert provider.calls == [["TCS"]]
        assert len(websocket_manager.subscriptions) == 1

    assert websocket_manager.clients == set()
    assert websocket_manager.subscriptions == {}


def test_unsubscribe_for_never_subscribed_symbol_is_idempotent(monkeypatch):
    provider = AcceptingSubscriptionProvider()
    monkeypatch.setattr(websocket_manager, "provider", provider)

    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "unsubscribe", "symbols": ["TCS"]})
        response = websocket.receive_json()

    assert response == {"status": "unsubscribed", "symbols": []}
    assert websocket_manager.subscriptions == {}


def test_disconnect_cleanup_is_idempotent_and_rejects_late_messages(monkeypatch):
    provider = AcceptingSubscriptionProvider()
    monkeypatch.setattr(websocket_manager, "provider", provider)
    connection = object()

    asyncio.run(websocket_manager.register_client(connection))
    asyncio.run(websocket_manager.subscribe(connection, ["TCS"]))
    asyncio.run(websocket_manager.unregister_client(connection))
    asyncio.run(websocket_manager.unregister_client(connection))
    response = asyncio.run(websocket_manager.subscribe(connection, ["INFY"]))

    assert response["status"] == "error"
    assert response["error"]["code"] == "client_not_connected"
    assert websocket_manager.clients == set()
    assert websocket_manager.subscriptions == {}


def test_unexpected_provider_error_is_sanitized_and_does_not_leave_state(monkeypatch):
    monkeypatch.setattr(websocket_manager, "provider", RaisingSubscriptionProvider())

    with client.websocket_connect("/ws/market") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["TCS"]})
        response = websocket.receive_json()

        assert response == {
            "status": "error",
            "error": {
                "code": "internal_error",
                "message": "Unable to process subscription.",
            },
        }
        assert "private provider diagnostic" not in str(response)
        assert websocket_manager.subscriptions == {}

        websocket.send_json({"action": "unsubscribe"})
        assert websocket.receive_json() == {"status": "unsubscribed", "symbols": []}

    assert websocket_manager.clients == set()
    assert websocket_manager.subscriptions == {}
