from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import websockets
from google.protobuf.message import DecodeError

from app.providers import upstox_market_data_feed_pb2 as feed_pb
from app.schemas.market import MarketQuote
from app.services.market_provider import ProviderConfigurationError

AUTHORIZATION_PATH = "/v3/feed/market-data-feed/authorize"
SUPPORTED_FEED_MODES = {"ltpc", "full", "option_greeks", "full_d30"}
MAX_FEED_FRAME_SIZE = 1_048_576

QuoteHandler = Callable[[MarketQuote], Awaitable[None] | None]
StatusHandler = Callable[[str], Awaitable[None] | None]


class UpstoxFeedAuthorizer:
    """Fetch the one-use V3 feed URL without exposing the token to clients."""

    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = "https://api.upstox.com",
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
        timeout: float = 20.0,
    ):
        self._access_token = access_token
        self._url = f"{base_url.rstrip('/')}{AUTHORIZATION_PATH}"
        self._client_factory = client_factory
        self._timeout = timeout

    async def get_authorized_websocket_url(self) -> str:
        if not self._access_token:
            raise ProviderConfigurationError("Upstox feed access token is not configured.")

        try:
            async with self._client_factory(timeout=self._timeout) as client:
                response = await client.get(
                    self._url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self._access_token}",
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderConfigurationError("Upstox feed authorization request failed.") from exc

        if response.status_code in {401, 403}:
            raise ProviderConfigurationError("Upstox feed authorization failed.")
        if response.status_code >= 400:
            raise ProviderConfigurationError("Upstox feed authorization is unavailable.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderConfigurationError("Upstox feed authorization returned malformed JSON.") from exc

        data = payload.get("data") if isinstance(payload, dict) else None
        authorized_url = data.get("authorized_redirect_uri") if isinstance(data, dict) else None
        if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(authorized_url, str):
            raise ProviderConfigurationError("Upstox feed authorization returned an invalid response.")

        try:
            parsed_url = urlsplit(authorized_url)
        except ValueError as exc:
            raise ProviderConfigurationError(
                "Upstox feed authorization returned an invalid WebSocket URL."
            ) from exc
        host = (parsed_url.hostname or "").lower()
        if (
            parsed_url.scheme != "wss"
            or not host
            or not (host == "upstox.com" or host.endswith(".upstox.com"))
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ProviderConfigurationError("Upstox feed authorization returned an invalid WebSocket URL.")
        return authorized_url


def build_subscription_message(
    instrument_keys: Sequence[str],
    *,
    mode: str | None = "ltpc",
    method: str = "sub",
) -> bytes:
    if isinstance(instrument_keys, (str, bytes)) or not instrument_keys:
        raise ValueError("instrument_keys must be a non-empty sequence")
    if not isinstance(method, str) or not isinstance(mode, (str, type(None))):
        raise ValueError("subscription method and mode must be strings")
    if method not in {"sub", "unsub", "change_mode"}:
        raise ValueError("unsupported Upstox subscription method")
    if method != "unsub" and mode not in SUPPORTED_FEED_MODES:
        raise ValueError("unsupported Upstox feed mode")

    keys = list(instrument_keys)
    for instrument_key in keys:
        if not isinstance(instrument_key, str):
            raise ValueError("instrument keys must be strings")
        parts = instrument_key.split("|")
        if (
            len(parts) != 2
            or not re.fullmatch(r"[A-Z0-9_]+", parts[0])
            or not parts[1].strip()
            or len(instrument_key) > 256
            or any(ord(character) < 32 for character in instrument_key)
        ):
            raise ValueError("invalid Upstox instrument key")
    if len(keys) != len(set(keys)):
        raise ValueError("instrument_keys must not contain duplicates")

    data: dict[str, Any] = {"instrumentKeys": keys}
    if method != "unsub":
        data["mode"] = mode
    message = {"guid": str(uuid4()), "method": method, "data": data}
    return json.dumps(message, separators=(",", ":")).encode("utf-8")


def _ltpc_from_feed(feed: Any):
    feed_kind = feed.WhichOneof("FeedUnion")
    if feed_kind == "ltpc":
        return feed.ltpc
    if feed_kind == "fullFeed":
        full_feed_kind = feed.fullFeed.WhichOneof("FullFeedUnion")
        if full_feed_kind == "marketFF":
            return feed.fullFeed.marketFF.ltpc
        if full_feed_kind == "indexFF":
            return feed.fullFeed.indexFF.ltpc
    if feed_kind == "firstLevelWithGreeks":
        return feed.firstLevelWithGreeks.ltpc
    return None


def decode_feed_frame(
    frame: bytes | bytearray | memoryview,
    key_to_symbol: Mapping[str, str],
) -> list[MarketQuote]:
    if not isinstance(frame, (bytes, bytearray, memoryview)):
        raise ProviderConfigurationError("Upstox feed frame must be binary.")
    if len(frame) > MAX_FEED_FRAME_SIZE:
        raise ProviderConfigurationError("Upstox feed frame exceeds the size limit.")

    response = feed_pb.FeedResponse()
    try:
        response.ParseFromString(bytes(frame))
    except DecodeError as exc:
        raise ProviderConfigurationError("Upstox returned a malformed Protobuf feed frame.") from exc

    if response.type not in {feed_pb.initial_feed, feed_pb.live_feed}:
        return []

    quotes = []
    for instrument_key, feed in response.feeds.items():
        symbol = key_to_symbol.get(instrument_key)
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9.-]{1,20}", symbol):
            continue
        ltpc = _ltpc_from_feed(feed)
        if ltpc is None or not math.isfinite(ltpc.ltp) or ltpc.ltp <= 0:
            continue

        previous_close = ltpc.cp if math.isfinite(ltpc.cp) and ltpc.cp > 0 else None
        change = ltpc.ltp - previous_close if previous_close is not None else None
        change_percent = change / previous_close * 100 if change is not None else None
        if change_percent is not None and not math.isfinite(change_percent):
            change_percent = None
        try:
            timestamp = (
                datetime.fromtimestamp(ltpc.ltt / 1000, tz=timezone.utc)
                if ltpc.ltt > 0
                else None
            )
        except (OverflowError, OSError, ValueError):
            timestamp = None

        quotes.append(
            MarketQuote(
                symbol=symbol,
                exchange=instrument_key.split("_", 1)[0],
                last_price=ltpc.ltp,
                previous_close=previous_close,
                change=change,
                change_percent=change_percent,
                timestamp=timestamp,
            )
        )
    return quotes


class UpstoxV3FeedClient:
    """Upstream Upstox transport, separate from the browser-facing WebSocket."""

    def __init__(
        self,
        authorizer: UpstoxFeedAuthorizer,
        *,
        websocket_connect: Callable[..., Any] = websockets.connect,
        mode: str = "ltpc",
        startup_timeout: float = 20.0,
        max_startup_attempts: int = 3,
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
    ):
        if mode not in SUPPORTED_FEED_MODES:
            raise ValueError("unsupported Upstox feed mode")
        self.authorizer = authorizer
        self.websocket_connect = websocket_connect
        self.mode = mode
        self.startup_timeout = startup_timeout
        self.max_startup_attempts = max_startup_attempts
        self.reconnect_initial_delay = reconnect_initial_delay
        self.reconnect_max_delay = reconnect_max_delay
        self._socket = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._connected = asyncio.Event()
        self._startup: asyncio.Future | None = None
        self._key_to_symbol: dict[str, str] = {}
        self._on_quote: QuoteHandler | None = None
        self._on_status: StatusHandler | None = None

    async def start(
        self,
        symbol_to_key: Mapping[str, str],
        *,
        on_quote: QuoteHandler,
        on_status: StatusHandler | None = None,
    ) -> None:
        if not symbol_to_key:
            raise ValueError("at least one symbol is required to start the feed")
        if self._task is not None:
            raise RuntimeError("Upstox feed client is already running")

        key_to_symbol: dict[str, str] = {}
        for symbol, instrument_key in symbol_to_key.items():
            if not isinstance(symbol, str) or not isinstance(instrument_key, str):
                raise ValueError("feed subscriptions must map symbols to instrument-key strings")
            if not re.fullmatch(r"[A-Z0-9.-]{1,20}", symbol):
                raise ValueError("feed subscription contains an invalid StockSense symbol")
            if instrument_key in key_to_symbol:
                raise ValueError("instrument keys must map to unique StockSense symbols")
            key_to_symbol[instrument_key] = symbol
        build_subscription_message(list(key_to_symbol), mode=self.mode)

        self._key_to_symbol = key_to_symbol
        self._on_quote = on_quote
        self._on_status = on_status
        self._stop_event = asyncio.Event()
        self._connected = asyncio.Event()
        self._startup = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(asyncio.shield(self._startup), timeout=self.startup_timeout)
        except asyncio.TimeoutError as exc:
            await self.stop()
            raise ProviderConfigurationError("Upstox feed connection timed out during startup.") from exc
        except Exception:
            await self.stop()
            raise

    async def _notify_status(self, status: str) -> None:
        if self._on_status is None:
            return
        try:
            result = self._on_status(status)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def _sleep_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _run(self) -> None:
        attempts = 0
        delay = self.reconnect_initial_delay
        connected_once = False
        while not self._stop_event.is_set():
            try:
                authorized_url = await self.authorizer.get_authorized_websocket_url()
                async with self.websocket_connect(
                    authorized_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=MAX_FEED_FRAME_SIZE,
                ) as socket:
                    self._socket = socket
                    await socket.send(
                        build_subscription_message(
                            list(self._key_to_symbol),
                            mode=self.mode,
                        )
                    )
                    self._connected.set()
                    if not connected_once:
                        connected_once = True
                        if self._startup is not None and not self._startup.done():
                            self._startup.set_result(None)
                    attempts = 0
                    delay = self.reconnect_initial_delay
                    await self._notify_status("connected")

                    async for frame in socket:
                        if self._stop_event.is_set():
                            break
                        try:
                            quotes = decode_feed_frame(frame, self._key_to_symbol)
                        except ProviderConfigurationError:
                            continue
                        for quote in quotes:
                            if self._on_quote is None:
                                continue
                            try:
                                result = self._on_quote(quote)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                continue
                self._socket = None
                self._connected.clear()
                if self._stop_event.is_set():
                    return
                await self._notify_status("disconnected")
            except asyncio.CancelledError:
                raise
            except ProviderConfigurationError as exc:
                self._socket = None
                self._connected.clear()
                if self._startup is not None and not self._startup.done():
                    self._startup.set_exception(exc)
                await self._notify_status("unavailable")
                return
            except Exception:
                self._socket = None
                self._connected.clear()
                attempts += 1
                if not connected_once and attempts >= self.max_startup_attempts:
                    if self._startup is not None and not self._startup.done():
                        self._startup.set_exception(
                            ProviderConfigurationError("Unable to establish the Upstox feed connection.")
                        )
                    return
                if connected_once:
                    await self._notify_status("disconnected")
                await self._sleep_or_stop(delay)
                delay = min(delay * 2, self.reconnect_max_delay)

    async def stop(self) -> None:
        self._stop_event.set()
        socket = self._socket
        self._socket = None
        if socket is not None:
            try:
                await socket.close()
            except Exception:
                pass

        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._connected.clear()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()