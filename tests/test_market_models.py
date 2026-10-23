from datetime import datetime

from app.schemas.market import HistoricalCandle, IndexQuote, MarketQuote, MarketStatus


def test_market_quote_validation():
    quote = MarketQuote(
        symbol="TCS",
        exchange="NSE",
        company_name="Tata Consultancy Services",
        last_price=3250.5,
        previous_close=3200.0,
        change=50.5,
        change_percent=1.58,
        open=3225.0,
        high=3268.0,
        low=3218.0,
        volume=1200000,
        timestamp=datetime.utcnow(),
        market_status="LIVE",
    )

    assert quote.symbol == "TCS"
    assert quote.exchange == "NSE"
    assert quote.last_price == 3250.5


def test_historical_candle_validation():
    candle = HistoricalCandle(
        symbol="RELIANCE",
        timestamp=datetime.utcnow(),
        open=2450.0,
        high=2495.0,
        low=2438.0,
        close=2478.0,
        volume=900000,
    )

    assert candle.close == 2478.0


def test_index_quote_validation():
    index = IndexQuote(
        symbol="NIFTY 50",
        exchange="NSE",
        name="NIFTY 50",
        value=24560.35,
        previous_close=24480.0,
        change=80.35,
        change_percent=0.33,
        timestamp=datetime.utcnow(),
        market_status="LIVE",
    )

    assert index.value == 24560.35
    assert index.symbol == "NIFTY 50"


def test_market_status_validation():
    status = MarketStatus(
        exchange="NSE",
        market_status="MARKET CLOSED",
        timestamp=datetime.utcnow(),
        message="Market is closed for the day.",
        is_open=False,
    )

    assert status.market_status == "MARKET CLOSED"
    assert status.is_open is False
