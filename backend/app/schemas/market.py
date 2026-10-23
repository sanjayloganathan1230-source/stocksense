from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MarketQuote(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    exchange: str = Field(..., min_length=1, max_length=20)
    company_name: str | None = None
    last_price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    timestamp: datetime | None = None
    market_status: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("symbol is required")
        if not cleaned.replace("-", "").replace(".", "").isalnum():
            raise ValueError("symbol contains unsupported characters")
        return cleaned


class HistoricalCandle(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class IndexQuote(BaseModel):
    symbol: str
    exchange: str
    name: str
    value: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    timestamp: datetime | None = None
    market_status: str | None = None


class MarketStatus(BaseModel):
    exchange: str
    market_status: Literal["LIVE", "MARKET CLOSED", "DELAYED", "HISTORICAL", "UNAVAILABLE", "DEMO DATA"]
    timestamp: datetime | None = None
    message: str | None = None
    is_open: bool = False
