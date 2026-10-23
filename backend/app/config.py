from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

MARKET_DATA_PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "").strip().lower()
MARKET_DATA_BASE_URL = os.getenv("MARKET_DATA_BASE_URL", "https://api.upstox.com")

UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_INSTRUMENT_MAP = os.getenv("UPSTOX_INSTRUMENT_MAP", "{}")

DATABASE_URL = os.getenv("DATABASE_URL", "")
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
