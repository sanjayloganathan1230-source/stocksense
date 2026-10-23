import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from google.protobuf.message import DecodeError

from app.providers import upstox_market_data_feed_pb2 as feed_pb
from app.providers.upstox_feed import (
    UpstoxFeedAuthorizer,
    UpstoxV3FeedClient,
    build_subscription_message,
    decode_feed_frame,
)
from app.providers.upstox_provider import UpstoxProvider
from app.services.market_provider import ProviderConfigurationError
from app.websocket.manager import StockSenseWebSocketManager

EQUITY_KEY = "NSE_EQ|TEST_INSTRUMENT"
INDEX_KEY = "NSE_INDEX|Test Index"
TEST_TOKEN = "offline-test-token"


def feed_frame(updates, *, feed_type=feed_pb.live_feed):
    response = feed_pb.FeedResponse(type=feed_type)
    for instrument_key, values in updates.items():
        quote = response.feeds[instrument_key].ltpc
        quote.ltp = values.get("ltp", 100.5)
        quote.ltt = values.get("ltt", 1_750_000_000_000)
        quote.ltq = values.get("ltq", 10)
        quote.cp = values.get("cp", 95.0)
    return response.SerializeToString()


class StaticAuthorizer:
    def __init__(self):
        self.calls = 0

    async def get_authorized_websocket_url(self):
        self.calls += 1
        return f"wss://feed.upstox.com/session/{self.calls}"


class QueueSocket:
    def __init__(self):
        self.sent = []
        self.frames = asyncio.Queue()
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        frame = await self.frames.get()
        if isinstance(frame, BaseException):
            raise frame
        if frame is None:
            raise StopAsyncIteration
        return frame

    async def send(self, frame):
        self.sent.append(frame)

    async def close(self):
        self.closed = True
        await self.frames.put(None)


class SocketContext:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.socket.close()


def test_feed_authorization_uses_backend_token_and_validates_response():
    captured = {}

    def handle_request(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["accept"] = request.headers["Accept"]
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"authorized_redirect_uri": "wss://feed.upstox.com/session/one-use"},
            },
        )

    def client_factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handle_request), **kwargs)

    authorizer = UpstoxFeedAuthorizer(
        access_token=TEST_TOKEN,
        client_factory=client_factory,
    )
    url = asyncio.run(authorizer.get_authorized_websocket_url())

    assert url == "wss://feed.upstox.com/session/one-use"
    assert captured == {
        "url": "https://api.upstox.com/v3/feed/market-data-feed/authorize",
        "authorization": f"Bearer {TEST_TOKEN}",
        "accept": "application/json",
    }


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_message"),
    [
        (401, {}, "authorization failed"),
        (200, {"status": "error", "data": {}}, "invalid response"),
        (
            200,
            {"status": "success", "data": {"authorized_redirect_uri": "https://bad.example/ws"}},
            "invalid WebSocket URL",
        ),
    ],
)
def test_feed_authorization_failures_are_sanitized(status_code, payload, expected_message):
    def client_factory(**kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))
        return httpx.AsyncClient(transport=transport, **kwargs)

    authorizer = UpstoxFeedAuthorizer(access_token=TEST_TOKEN, client_factory=client_factory)
    with pytest.raises(ProviderConfigurationError, match=expected_message) as error:
        asyncio.run(authorizer.get_authorized_websocket_url())

    assert TEST_TOKEN not in str(error.value)


def test_missing_feed_token_fails_without_request():
    authorizer = UpstoxFeedAuthorizer(access_token="")

    with pytest.raises(ProviderConfigurationError, match="access token is not configured"):
        asyncio.run(authorizer.get_authorized_websocket_url())


def test_subscription_envelope_is_upstox_v3_binary_json():
    encoded = build_subscription_message([EQUITY_KEY], mode="ltpc")
    request = json.loads(encoded)

    assert isinstance(encoded, bytes)
    assert request["method"] == "sub"
    assert request["data"] == {"mode": "ltpc", "instrumentKeys": [EQUITY_KEY]}
    assert request["guid"]


@pytest.mark.parametrize(
    "keys",
    [[], [EQUITY_KEY, EQUITY_KEY], ["invalid-key"], [{}]],
)
def test_subscription_conversion_rejects_invalid_keys(keys):
    with pytest.raises(ValueError):
        build_subscription_message(keys)


@pytest.mark.parametrize(("method", "mode"), [([], "ltpc"), ("sub", {})])
def test_subscription_builder_rejects_non_string_controls(method, mode):
    with pytest.raises(ValueError):
        build_subscription_message([EQUITY_KEY], method=method, mode=mode)


def test_upstox_provider_resolves_symbols_and_rejects_unmapped_or_duplicate_symbols():
    provider = UpstoxProvider(
        access_token=TEST_TOKEN,
        instrument_map={"TCS": EQUITY_KEY, "NIFTY": INDEX_KEY},
    )

    assert provider.resolve_live_quote_symbols(["TCS", "NIFTY"]) == {
        "TCS": EQUITY_KEY,
        "NIFTY": INDEX_KEY,
    }
    with pytest.raises(ProviderConfigurationError, match="UPSTOX_INSTRUMENT_MAP"):
        provider.resolve_live_quote_symbols(["UNKNOWN"])
    with pytest.raises(ValueError, match="duplicates"):
        provider.resolve_live_quote_symbols(["TCS", "TCS"])
    with pytest.raises(ValueError, match="non-empty"):
        provider.resolve_live_quote_symbols([])
    with pytest.raises(ValueError, match="string"):
        provider.resolve_live_quote_symbols([{}])


def test_protobuf_ltp_frame_maps_to_normalized_stock_quote():
    quotes = decode_feed_frame(
        feed_frame({EQUITY_KEY: {"ltp": 100.5, "cp": 95.0, "ltq": 99}}),
        {EQUITY_KEY: "TCS"},
    )

    assert len(quotes) == 1
    quote = quotes[0]
    assert quote.symbol == "TCS"
    assert quote.exchange == "NSE"
    assert quote.last_price == 100.5
    assert quote.previous_close == 95.0
    assert quote.change == 5.5
    assert quote.change_percent == pytest.approx(5.7894736842)
    assert quote.timestamp == datetime.fromtimestamp(1_750_000_000, tz=timezone.utc)
    assert quote.volume is None


def test_protobuf_decoding_maps_keys_and_ignores_unmapped_or_unusable_updates():
    quotes = decode_feed_frame(
        feed_frame(
            {
                EQUITY_KEY: {"ltp": 100.0},
                INDEX_KEY: {"ltp": 0.0},
                "NSE_EQ|UNMAPPED": {"ltp": 50.0},
            }
        ),
        {EQUITY_KEY: "TCS", INDEX_KEY: "NIFTY"},
    )

    assert [quote.symbol for quote in quotes] == ["TCS"]


def test_protobuf_decoder_handles_unknown_and_unsupported_feed_types():
    assert decode_feed_frame(feed_frame({}, feed_type=feed_pb.market_info), {}) == []

    response = feed_pb.FeedResponse(type=99)
    assert decode_feed_frame(response.SerializeToString(), {}) == []

    response = feed_pb.FeedResponse(type=feed_pb.live_feed)
    response.feeds[EQUITY_KEY].fullFeed.indexFF.ltpc.ltp = 101.0
    quotes = decode_feed_frame(response.SerializeToString(), {EQUITY_KEY: "NIFTY"})
    assert len(quotes) == 1
    assert quotes[0].symbol == "NIFTY"


def test_extreme_feed_values_do_not_produce_infinite_normalized_percent():
    quotes = decode_feed_frame(
        feed_frame({EQUITY_KEY: {"ltp": 1e308, "cp": 5e-324}}),
        {EQUITY_KEY: "TCS"},
    )

    assert len(quotes) == 1
    assert quotes[0].change_percent is None


def test_malformed_protobuf_frames_are_rejected_safely():
    with pytest.raises(ProviderConfigurationError, match="malformed Protobuf"):
        decode_feed_frame(b"\x80", {EQUITY_KEY: "TCS"})

    with pytest.raises(ProviderConfigurationError, match="size limit"):
        decode_feed_frame(bytes(1_048_577), {})


class RecordingBrowserSocket:
    def __init__(self):
        self.messages = []
        self.quote_received = asyncio.Event()

    async def send_json(self, message):
        self.messages.append(message)
        if "symbol" in message:
            self.quote_received.set()


def test_manager_broadcasts_only_normalized_quotes_to_matching_clients():
    async def verify():
        authorizer = StaticAuthorizer()
        upstream_sockets = []

        def connect(url, **kwargs):
            socket = QueueSocket()
            upstream_sockets.append(socket)
            return SocketContext(socket)

        provider = UpstoxProvider(
            access_token=TEST_TOKEN,
            instrument_map={"TCS": EQUITY_KEY, "NIFTY": INDEX_KEY},
            feed_authorizer=authorizer,
            websocket_connect=connect,
        )
        manager = StockSenseWebSocketManager(provider=provider)
        tcs_client = RecordingBrowserSocket()
        nifty_client = RecordingBrowserSocket()
        await manager.register_client(tcs_client)
        await manager.register_client(nifty_client)

        await manager.subscribe(tcs_client, ["TCS"])
        await manager.subscribe(nifty_client, ["NIFTY"])
        current_socket = upstream_sockets[-1]
        subscription = json.loads(current_socket.sent[0])
        assert set(subscription["data"]["instrumentKeys"]) == {EQUITY_KEY, INDEX_KEY}

        await current_socket.frames.put(
            feed_frame({EQUITY_KEY: {"ltp": 101.0}, INDEX_KEY: {"ltp": 202.0}})
        )
        await asyncio.wait_for(
            asyncio.gather(tcs_client.quote_received.wait(), nifty_client.quote_received.wait()),
            timeout=1,
        )

        tcs_quotes = [message for message in tcs_client.messages if "symbol" in message]
        nifty_quotes = [message for message in nifty_client.messages if "symbol" in message]
        assert [message["symbol"] for message in tcs_quotes] == ["TCS"]
        assert [message["symbol"] for message in nifty_quotes] == ["NIFTY"]
        assert "instrument_key" not in tcs_quotes[0]
        assert TEST_TOKEN not in str(tcs_client.messages + nifty_client.messages)
        assert "one-use" not in str(tcs_client.messages + nifty_client.messages)
        await manager.unregister_client(tcs_client)
        assert manager._feed_symbols == {"NIFTY": INDEX_KEY}
        await manager.unregister_client(nifty_client)
        assert manager._feed_client is None
        await manager.close()

    asyncio.run(verify())


def test_upstream_connection_retries_without_exposing_transport_errors():
    async def verify():
        authorizer = StaticAuthorizer()
        sockets = []
        attempts = 0

        def connect(url, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError(f"private transport detail {TEST_TOKEN}")
            socket = QueueSocket()
            sockets.append(socket)
            return SocketContext(socket)

        client = UpstoxV3FeedClient(
            authorizer,
            websocket_connect=connect,
            startup_timeout=1,
            max_startup_attempts=3,
            reconnect_initial_delay=0.001,
            reconnect_max_delay=0.01,
        )
        statuses = []
        await client.start({"TCS": EQUITY_KEY}, on_quote=lambda quote: None, on_status=statuses.append)
        assert attempts == 2
        assert "connected" in statuses
        assert TEST_TOKEN not in str(statuses)
        await client.stop()

    asyncio.run(verify())


def test_upstream_disconnect_reauthorizes_and_reconnects():
    async def verify():
        authorizer = StaticAuthorizer()
        sockets = []
        second_connection = asyncio.Event()

        def connect(url, **kwargs):
            socket = QueueSocket()
            sockets.append(socket)
            return SocketContext(socket)

        async def record_status(status):
            if status == "connected" and len(sockets) == 2:
                second_connection.set()

        client = UpstoxV3FeedClient(
            authorizer,
            websocket_connect=connect,
            startup_timeout=1,
            reconnect_initial_delay=0.001,
            reconnect_max_delay=0.01,
        )
        await client.start({"TCS": EQUITY_KEY}, on_quote=lambda quote: None, on_status=record_status)
        await sockets[0].frames.put(ConnectionError("private disconnect detail"))
        await asyncio.wait_for(second_connection.wait(), timeout=1)
        assert authorizer.calls == 2
        assert len(sockets) == 2
        await client.stop()

    asyncio.run(verify())