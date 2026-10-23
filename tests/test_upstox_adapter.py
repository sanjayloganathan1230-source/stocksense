from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.providers.instrument_resolver import InstrumentResolver
from app.providers.upstox_provider import UpstoxProvider
from app.services.market_provider import ProviderConfigurationError
from app.main import app


EQUITY_KEY = "NSE_EQ|TEST_INSTRUMENT"
INDEX_KEY = "NSE_INDEX|Test Index"
QUOTE_TIMESTAMP_MS = 1_750_000_000_000
client = TestClient(app)


def make_provider():
    return UpstoxProvider(
        access_token="offline-test-token",
        instrument_map={"TCS": EQUITY_KEY, "NIFTY": INDEX_KEY},
    )


def make_http_response(payload=None, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def quote_payload(instrument_key=EQUITY_KEY, **record_changes):
    record = {
        "instrument_token": instrument_key,
        "last_price": 3450.5,
        "prev_ohlc": {
            "open": 3400.0,
            "high": 3440.0,
            "low": 3380.0,
            "close": 3400.0,
            "volume": 100000,
            "ts": QUOTE_TIMESTAMP_MS - 86400000,
        },
        "live_ohlc": {
            "open": 3410.0,
            "high": 3465.0,
            "low": 3398.0,
            "close": 3450.5,
            "volume": 1500000,
            "ts": QUOTE_TIMESTAMP_MS,
        },
    }
    record.update(record_changes)
    response_key = instrument_key.replace("|", ":")
    return {"status": "success", "data": {response_key: record}}


def test_upstox_provider_requires_an_access_token():
    with pytest.raises(ProviderConfigurationError, match="UPSTOX_ACCESS_TOKEN"):
        UpstoxProvider(access_token="")


def test_instrument_resolver_uses_configured_keys():
    resolver = InstrumentResolver(instrument_map={"tcs": EQUITY_KEY})

    assert resolver.resolve_symbol("tcs") == EQUITY_KEY
    assert resolver.resolve_symbol("unknown") == "UNKNOWN"
    assert resolver.get_mapping() == {"TCS": EQUITY_KEY}


@pytest.mark.parametrize(
    "instrument_map",
    [
        "{invalid-json",
        [],
        {"broken": ""},
        {"wrong_type": 123},
    ],
)
def test_invalid_instrument_map_fails_clearly(instrument_map):
    with pytest.raises(ProviderConfigurationError, match="UPSTOX_INSTRUMENT_MAP"):
        InstrumentResolver(instrument_map=instrument_map)


def test_provider_requires_a_mapping_for_each_symbol():
    provider = UpstoxProvider(access_token="offline-test-token", instrument_map={})

    with pytest.raises(ProviderConfigurationError, match="UPSTOX_INSTRUMENT_MAP"):
        provider.get_quote("TCS")


def test_live_subscription_resolves_keys_without_claiming_streaming():
    result = make_provider().subscribe_live_quotes(["TCS"])

    assert result == {
        "provider": "upstox",
        "subscription_symbols": [EQUITY_KEY],
        "status": "prepared",
    }


@patch("app.providers.upstox_provider.httpx.get")
def test_quote_response_and_v3_request_are_normalized(mock_get):
    mock_get.return_value = make_http_response(quote_payload())

    quote = make_provider().get_quote("tcs")

    assert quote.symbol == "TCS"
    assert quote.exchange == "NSE"
    assert quote.last_price == 3450.5
    assert quote.previous_close == 3400.0
    assert quote.change == 50.5
    assert quote.change_percent == pytest.approx(1.4852941176)
    assert quote.open == 3410.0
    assert quote.high == 3465.0
    assert quote.low == 3398.0
    assert quote.volume == 1500000
    assert quote.timestamp == datetime.fromtimestamp(QUOTE_TIMESTAMP_MS / 1000).astimezone()
    assert quote.market_status is None

    request = mock_get.call_args
    assert request.args[0] == "https://api.upstox.com/v3/market-quote/ohlc"
    assert request.kwargs["params"] == {"instrument_key": EQUITY_KEY, "interval": "1d"}
    assert request.kwargs["headers"]["Authorization"] == "Bearer offline-test-token"
    assert "Api-Key" not in request.kwargs["headers"]


@patch("app.providers.upstox_provider.httpx.get")
def test_index_response_is_normalized(mock_get):
    mock_get.return_value = make_http_response(quote_payload(INDEX_KEY))

    index = make_provider().get_index_quote("NIFTY")

    assert index.symbol == "NIFTY"
    assert index.name == "NIFTY"
    assert index.value == 3450.5
    assert index.previous_close == 3400.0
    assert index.change == 50.5
    assert index.change_percent == pytest.approx(1.4852941176)
    assert index.timestamp is not None
    assert index.market_status is None
    assert mock_get.call_args.kwargs["params"]["instrument_key"] == INDEX_KEY


@patch("app.providers.upstox_provider.httpx.get")
def test_historical_candles_use_v3_path_and_normalize(mock_get):
    mock_get.return_value = make_http_response(
        {
            "status": "success",
            "data": {
                "candles": [
                    ["2025-01-01T09:15:00+05:30", 100, 104, 98, 102, 5000, 0],
                    ["2025-01-02T09:15:00+05:30", 102, 106, 101, 105, 4500, 0],
                ]
            },
        }
    )

    candles = make_provider().get_historical_data("TCS", "1m")

    assert len(candles) == 2
    assert candles[0].symbol == "TCS"
    assert candles[0].timestamp.isoformat() == "2025-01-01T09:15:00+05:30"
    assert candles[0].close == 102.0
    assert candles[0].volume == 5000
    url = mock_get.call_args.args[0]
    assert "/v3/historical-candle/NSE_EQ%7CTEST_INSTRUMENT/days/1/" in url
    to_date, from_date = [date.fromisoformat(part) for part in url.rsplit("/", 2)[1:]]
    assert to_date == date.today()
    assert to_date - from_date == timedelta(days=29)
    assert mock_get.call_args.kwargs["params"] is None


@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (401, "authentication failed"),
        (403, "authentication failed"),
        (404, "not found"),
        (429, "rate limit"),
        (503, "provider unavailable"),
    ],
)
@patch("app.providers.upstox_provider.httpx.get")
def test_http_errors_become_controlled_provider_errors(mock_get, status_code, message):
    mock_get.return_value = make_http_response(status_code=status_code)

    with pytest.raises(ProviderConfigurationError, match=message):
        make_provider().get_quote("TCS")


@patch("app.providers.upstox_provider.httpx.get")
def test_malformed_json_becomes_controlled_provider_error(mock_get):
    response = make_http_response()
    response.json.side_effect = ValueError("invalid JSON")
    mock_get.return_value = response

    with pytest.raises(ProviderConfigurationError, match="malformed JSON"):
        make_provider().get_quote("TCS")


@pytest.mark.parametrize(
    "record_changes",
    [
        {"instrument_token": "NSE_EQ|WRONG"},
        {"last_price": None},
        {"last_price": "not-a-price"},
        {"live_ohlc": []},
    ],
)
@patch("app.providers.upstox_provider.httpx.get")
def test_invalid_quote_contract_fails_safely(mock_get, record_changes):
    mock_get.return_value = make_http_response(quote_payload(**record_changes))

    with pytest.raises(ProviderConfigurationError):
        make_provider().get_quote("TCS")


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "success", "data": {}},
        {"status": "success", "data": {"candles": [["2025-01-01", 1, 2, 0, 1]]}},
        {"status": "success", "data": {"candles": [["invalid-date", 1, 2, 0, 1, 10]]}},
        {"status": "error", "data": {"candles": []}},
    ],
)
@patch("app.providers.upstox_provider.httpx.get")
def test_invalid_historical_contract_fails_safely(mock_get, payload):
    mock_get.return_value = make_http_response(payload)

    with pytest.raises(ProviderConfigurationError):
        make_provider().get_historical_data("TCS")


@patch("app.api.market_routes.market_data_service.get_quote")
def test_provider_error_becomes_controlled_api_response(mock_get):
    mock_get.side_effect = ProviderConfigurationError("Upstox authentication failed.")

    response = client.get("/api/market/quote/TCS")

    assert response.status_code == 503
    assert response.json()["detail"] == "Upstox authentication failed."
