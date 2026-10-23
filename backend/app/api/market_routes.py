from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.market_provider import ProviderConfigurationError
from app.services.market_service import market_data_service

router = APIRouter(prefix="/api/market", tags=["market"])


def _provider_unavailable(exc: ProviderConfigurationError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/quote/{symbol}")
def get_quote(symbol: str):
    try:
        return market_data_service.get_quote(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise _provider_unavailable(exc) from exc
    except Exception as exc:  # pragma: no cover - provider-specific exceptions
        raise HTTPException(
            status_code=503,
            detail="Market data provider is not configured. Set provider credentials and configuration first.",
        ) from exc


@router.get("/historical/{symbol}")
def get_historical_data(symbol: str, interval: str = Query(default="1d")):
    try:
        return market_data_service.get_historical_data(symbol, interval)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise _provider_unavailable(exc) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="Market data provider is not configured. Set provider credentials and configuration first.",
        ) from exc


@router.get("/index/{symbol}")
def get_index_quote(symbol: str):
    try:
        return market_data_service.get_index_quote(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise _provider_unavailable(exc) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="Market data provider is not configured. Set provider credentials and configuration first.",
        ) from exc


@router.get("/status")
def get_market_status(exchange: str = "NSE"):
    try:
        return market_data_service.get_market_status(exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise _provider_unavailable(exc) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="Market data provider is not configured. Set provider credentials and configuration first.",
        ) from exc


@router.get("/search")
def search_symbols(query: str = Query(default=""), limit: int = Query(default=8, ge=1, le=20)):
    return market_data_service.search_symbols(query, limit)


@router.get("/movers")
def get_market_movers():
    try:
        return market_data_service.get_market_movers()
    except ProviderConfigurationError as exc:
        raise _provider_unavailable(exc) from exc


@router.get("/activity")
def get_market_activity():
    try:
        return market_data_service.get_market_activity()
    except ProviderConfigurationError as exc:
        raise _provider_unavailable(exc) from exc
