from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.market_provider import ProviderConfigurationError
from app.services.market_service import market_data_service
from app.websocket.manager import StockSenseWebSocketManager

router = APIRouter(tags=["websocket"])
manager = StockSenseWebSocketManager(provider=market_data_service.provider)
MAX_WEBSOCKET_MESSAGE_LENGTH = 8192


def _error_response(code: str, message: str) -> dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message}}


@router.websocket("/ws/market")
async def market_websocket(websocket: WebSocket):
    await websocket.accept()
    await manager.register_client(websocket)

    try:
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                break

            raw_message = frame.get("text")
            if raw_message is None:
                await websocket.send_json(_error_response("invalid_message", "Message must be text."))
                continue

            if len(raw_message) > MAX_WEBSOCKET_MESSAGE_LENGTH:
                await websocket.send_json(_error_response("message_too_large", "Message exceeds the size limit."))
                continue

            if not raw_message.strip():
                await websocket.send_json(_error_response("empty_message", "Message must not be empty."))
                continue

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json(_error_response("malformed_json", "Message must be valid JSON."))
                continue

            if not isinstance(message, dict):
                await websocket.send_json(_error_response("invalid_message", "Message must be a JSON object."))
                continue

            action = message.get("action")
            if not isinstance(action, str) or not action.strip():
                await websocket.send_json(_error_response("missing_action", "Message requires an action."))
                continue
            action = action.strip().lower()

            if action == "subscribe":
                if "symbols" not in message:
                    await websocket.send_json(_error_response("missing_symbols", "Subscribe requires symbols."))
                    continue

                symbols = message["symbols"]
                if not isinstance(symbols, list):
                    await websocket.send_json(_error_response("invalid_symbols", "Symbols must be a list of strings."))
                    continue
                try:
                    response = await manager.subscribe(websocket, symbols)
                except ValueError as exc:
                    response = _error_response("invalid_symbols", str(exc))
                except ProviderConfigurationError as exc:
                    response = {"status": "unavailable", "message": str(exc)}
                except Exception:
                    response = _error_response("internal_error", "Unable to process subscription.")
            elif action == "unsubscribe":
                symbols = message.get("symbols")
                if symbols is not None and not isinstance(symbols, list):
                    await websocket.send_json(_error_response("invalid_symbols", "Symbols must be a list of strings."))
                    continue
                try:
                    response = await manager.unsubscribe(websocket, symbols)
                except ValueError as exc:
                    response = _error_response("invalid_symbols", str(exc))
            else:
                response = _error_response("unknown_action", "Unsupported action.")

            await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.send_json(_error_response("internal_error", "Unable to process message."))
        except Exception:
            pass
    finally:
        await manager.unregister_client(websocket)
