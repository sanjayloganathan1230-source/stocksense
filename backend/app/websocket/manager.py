from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Any

class StockSenseWebSocketManager:
    """Server-side coordinator for client subscriptions and provider streaming state."""

    MAX_SUBSCRIPTION_SYMBOLS = 50
    MAX_SYMBOL_LENGTH = 20

    def __init__(self, provider=None):
        self.provider = provider
        self.clients: set[Any] = set()
        self.subscriptions: dict[str, set[str]] = defaultdict(set)
        self.stream_status = "not_started" if getattr(provider, "streaming_available", False) else "unavailable"
        self._feed_client = None
        self._feed_symbols: dict[str, str] = {}
        self._subscription_lock = asyncio.Lock()

    def configure_provider(self, provider):
        self.provider = provider
        self.stream_status = "not_started" if getattr(provider, "streaming_available", False) else "unavailable"
        return self.provider

    async def register_client(self, websocket):
        self.clients.add(websocket)

    async def unregister_client(self, websocket):
        if self._supports_managed_feed():
            async with self._subscription_lock:
                self.clients.discard(websocket)
                self.subscriptions.pop(str(id(websocket)), None)
                try:
                    all_symbols = sorted(self._all_subscribed_symbols())
                    symbol_to_key = self.provider.resolve_live_quote_symbols(all_symbols) if all_symbols else {}
                    await self._set_upstream_subscriptions(symbol_to_key)
                except Exception:
                    self.stream_status = "unavailable"
            return
        self.clients.discard(websocket)
        self.subscriptions.pop(str(id(websocket)), None)

    @staticmethod
    def normalize_symbols(symbols: list[str]) -> list[str]:
        if not isinstance(symbols, list) or not symbols:
            raise ValueError("symbols must be a non-empty list")
        if len(symbols) > StockSenseWebSocketManager.MAX_SUBSCRIPTION_SYMBOLS:
            raise ValueError("too many symbols in subscription")

        normalized = []
        for symbol in symbols:
            if not isinstance(symbol, str):
                raise ValueError("each symbol must be a string")
            cleaned = symbol.strip().upper()
            if not cleaned:
                raise ValueError("symbols must not be empty")
            if len(cleaned) > StockSenseWebSocketManager.MAX_SYMBOL_LENGTH or not re.fullmatch(
                r"[A-Z0-9.-]+", cleaned
            ):
                raise ValueError("symbols contain unsupported characters")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _client_key(websocket) -> str:
        return str(id(websocket))

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"status": "error", "error": {"code": code, "message": message}}

    def _supports_managed_feed(self) -> bool:
        return callable(getattr(self.provider, "resolve_live_quote_symbols", None)) and callable(
            getattr(self.provider, "create_live_quote_feed_client", None)
        )

    def _all_subscribed_symbols(self) -> set[str]:
        return set().union(*self.subscriptions.values()) if self.subscriptions else set()

    async def _broadcast_status(self, status: str) -> None:
        if status == "demo_connected":
            self.stream_status = "demo"
            message = {
                "status": "demo",
                "message": "Demo/synthetic market data — not real-time market data",
            }
        elif status == "connected":
            self.stream_status = "connected"
            message = {"status": "subscribed", "message": "Upstream market-data feed connected."}
        elif status == "disconnected":
            self.stream_status = "disconnected"
            message = {"status": "unavailable", "message": "Market-data feed disconnected; reconnecting."}
        else:
            self.stream_status = "unavailable"
            message = {"status": "unavailable", "message": "Upstream market-data feed is unavailable."}

        for websocket in tuple(self.clients):
            if self.subscriptions.get(self._client_key(websocket)):
                try:
                    await websocket.send_json(message)
                except Exception:
                    continue

    async def _broadcast_quote(self, quote) -> None:
        payload = quote.model_dump(mode="json")
        for websocket in tuple(self.clients):
            if quote.symbol not in self.subscriptions.get(self._client_key(websocket), set()):
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                continue

    async def _set_upstream_subscriptions(self, symbol_to_key: dict[str, str]) -> None:
        if symbol_to_key == self._feed_symbols and self._feed_client is not None:
            if self._feed_client.is_running:
                return

        previous_client = self._feed_client
        self._feed_client = None
        self._feed_symbols = {}
        if previous_client is not None:
            await previous_client.stop()

        if not symbol_to_key:
            self.stream_status = "not_started" if getattr(self.provider, "streaming_available", False) else "unavailable"
            return

        feed_client = None
        try:
            feed_client = self.provider.create_live_quote_feed_client()
            await feed_client.start(
                symbol_to_key,
                on_quote=self._broadcast_quote,
                on_status=self._broadcast_status,
            )
        except Exception:
            if feed_client is not None:
                await feed_client.stop()
            self.stream_status = "unavailable"
            raise

        self._feed_client = feed_client
        self._feed_symbols = dict(symbol_to_key)

    async def subscribe(self, websocket, symbols: list[str]) -> dict[str, Any]:
        if websocket not in self.clients:
            return self._error("client_not_connected", "Client is not connected.")

        normalized = self.normalize_symbols(symbols)
        client_key = self._client_key(websocket)
        existing = self.subscriptions.get(client_key, set())
        pending = [symbol for symbol in normalized if symbol not in existing]
        if not pending:
            if (
                existing
                and self._supports_managed_feed()
                and (self._feed_client is None or not self._feed_client.is_running)
            ):
                async with self._subscription_lock:
                    all_symbols = sorted(self._all_subscribed_symbols())
                    mapping = self.provider.resolve_live_quote_symbols(all_symbols)
                    await self._set_upstream_subscriptions(mapping)
            if getattr(self.provider, "data_mode", None) == "demo":
                return {
                    "status": "demo",
                    "symbols": normalized,
                    "message": "Demo/synthetic market data — not real-time market data",
                }
            return {"status": "subscribed", "symbols": normalized}

        if self._supports_managed_feed():
            async with self._subscription_lock:
                current = self.subscriptions.get(client_key, set()).copy()
                self.subscriptions.setdefault(client_key, set()).update(pending)
                try:
                    all_symbols = sorted(self._all_subscribed_symbols())
                    symbol_to_key = self.provider.resolve_live_quote_symbols(all_symbols)
                    await self._set_upstream_subscriptions(symbol_to_key)
                except Exception:
                    if current:
                        self.subscriptions[client_key] = current
                    else:
                        self.subscriptions.pop(client_key, None)
                    self.stream_status = "unavailable"
                    await self._broadcast_status("unavailable")
                    raise
            if self.provider.data_mode == "demo":
                return {
                    "status": "demo",
                    "symbols": normalized,
                    "message": "Demo/synthetic market data — not real-time market data",
                }
            return {"status": "subscribed", "symbols": normalized}

        if self.provider is None:
            return {"status": "unavailable", "message": "Live market-data streaming is not configured."}

        provider_result = self.provider.subscribe_live_quotes(pending)
        if not isinstance(provider_result, dict) or provider_result.get("status") != "subscribed":
            message = (
                provider_result.get("message")
                if isinstance(provider_result, dict) and isinstance(provider_result.get("message"), str)
                else None
            )
            message = message or "Live market-data streaming is not available."
            return {"status": "unavailable", "message": message}

        self.subscriptions.setdefault(client_key, set()).update(pending)
        return {"status": "subscribed", "symbols": normalized}

    async def unsubscribe(self, websocket, symbols: list[str] | None = None) -> dict[str, Any]:
        if websocket not in self.clients:
            return self._error("client_not_connected", "Client is not connected.")

        client_key = self._client_key(websocket)
        if self._supports_managed_feed():
            async with self._subscription_lock:
                removed = self._remove_client_subscriptions(client_key, symbols)
                try:
                    all_symbols = sorted(self._all_subscribed_symbols())
                    symbol_to_key = self.provider.resolve_live_quote_symbols(all_symbols) if all_symbols else {}
                    await self._set_upstream_subscriptions(symbol_to_key)
                except Exception:
                    self.stream_status = "unavailable"
            return {"status": "unsubscribed", "symbols": removed}

        current = self.subscriptions.get(client_key, set())
        removed = self._remove_client_subscriptions(client_key, symbols)
        return {"status": "unsubscribed", "symbols": removed}

    def _remove_client_subscriptions(self, client_key: str, symbols: list[str] | None) -> list[str]:
        current = self.subscriptions.get(client_key, set())
        if symbols is None:
            removed = sorted(current)
            self.subscriptions.pop(client_key, None)
        else:
            normalized = self.normalize_symbols(symbols)
            removed = [symbol for symbol in normalized if symbol in current]
            remaining = current.difference(removed)
            if remaining:
                self.subscriptions[client_key] = remaining
            else:
                self.subscriptions.pop(client_key, None)
        return removed

    async def close(self):
        feed_client = self._feed_client
        self._feed_client = None
        self._feed_symbols = {}
        if feed_client is not None:
            await feed_client.stop()
        self.clients.clear()
        self.subscriptions.clear()
        self.stream_status = "unavailable"
