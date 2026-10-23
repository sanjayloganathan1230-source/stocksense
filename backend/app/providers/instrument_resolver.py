from __future__ import annotations

import json

from app.config import UPSTOX_INSTRUMENT_MAP
from app.services.market_provider import ProviderConfigurationError


class InstrumentResolver:
    """Resolve internal StockSense symbols to provider instrument identifiers."""

    def __init__(self, instrument_map: str | dict | None = None):
        raw_map = UPSTOX_INSTRUMENT_MAP if instrument_map is None else instrument_map
        if isinstance(raw_map, str):
            try:
                raw_map = json.loads(raw_map or "{}")
            except json.JSONDecodeError as exc:
                raise ProviderConfigurationError(
                    "UPSTOX_INSTRUMENT_MAP must contain a valid JSON object."
                ) from exc

        if not isinstance(raw_map, dict):
            raise ProviderConfigurationError("UPSTOX_INSTRUMENT_MAP must contain a JSON object.")

        self._map = {}
        for symbol, instrument_key in raw_map.items():
            if not isinstance(symbol, str) or not isinstance(instrument_key, str):
                raise ProviderConfigurationError(
                    "UPSTOX_INSTRUMENT_MAP entries must map symbols to instrument-key strings."
                )
            cleaned_symbol = symbol.strip().upper()
            cleaned_key = instrument_key.strip()
            key_parts = cleaned_key.split("|")
            if not cleaned_symbol or len(key_parts) != 2 or not all(key_parts):
                raise ProviderConfigurationError(
                    "UPSTOX_INSTRUMENT_MAP entries require a symbol and an exchange|instrument key."
                )
            self._map[cleaned_symbol] = cleaned_key

    def resolve_symbol(self, symbol: str) -> str:
        cleaned = symbol.strip().upper()
        if not cleaned:
            raise ValueError('symbol is required')

        if cleaned in self._map:
            return str(self._map[cleaned])

        return cleaned

    def resolve_symbols(self, symbols: list[str]) -> list[str]:
        return [self.resolve_symbol(symbol) for symbol in symbols]

    def get_provider_key(self, symbol: str) -> str:
        return self.resolve_symbol(symbol)

    def get_mapping(self) -> dict[str, str]:
        return dict(self._map)
