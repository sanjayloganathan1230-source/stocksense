# StockSense

StockSense is a final-year project that visualizes live Indian stock-market data through a modern dashboard built with React, FastAPI, PostgreSQL, and Python-based analytics tooling.

<img width="1536" height="1024" alt="StockSense Indian Market Dashboard" src="https://github.com/user-attachments/assets/1b08caf3-1119-4535-a102-5484a481d68f" />


## Project purpose

<img width="1536" height="1024" alt="Reliance Industries Stock Dashboard" src="https://github.com/user-attachments/assets/220794d3-649c-4a05-ba4f-409f63579bac" />

The goal of StockSense is to provide a professional, responsive dashboard for:

- live Indian market overview
- stock and index monitoring
- sector performance
- chart exploration
- basic analytics and AI/ML learning workflows

This project is designed as a scalable platform. The current stage focuses on architecture, environment setup, and a working backend/frontend connection test.

<img width="1536" height="1024" alt="StockSense Dark Finance Watchlist Dashboard" src="https://github.com/user-attachments/assets/fc0c68a5-aaf4-47a2-b51e-5c54c7760161" />


## Technology stack

- Frontend: React + Vite + JavaScript
- Backend: Python + FastAPI
- Data processing: Pandas + NumPy
- Database: PostgreSQL
- AI/ML: Python + scikit-learn
- API design: REST-first, with room for WebSockets later

## Current architecture

The current live-data architecture is:

Frontend
→ FastAPI
→ MarketDataService
→ Provider Adapter
→ Market Data API

This keeps the app provider-neutral. Select `demo` for local synthetic datasets or `upstox` for provider data; React uses the same backend contract for either mode.

<img width="1536" height="1024" alt="Neon Dark Finance Portfolio Dashboard" src="https://github.com/user-attachments/assets/42a6b0f4-31c3-4e94-9e0b-4a48400e3f93" />


## System architecture

The overall flow is:

1. Market Data Provider
   - Fetches real market data from a legitimate Indian market API/data provider.
2. FastAPI backend
   - Exposes REST endpoints and coordinates data collection and validation.
3. MarketDataService
   - Provides a provider-neutral service for symbols, quotes, historical data, and market status.
4. Provider Adapter
   - Converts provider-specific responses into the platform's internal schemas.
5. Data processing layer
   - Cleans, transforms, and normalizes raw data.
6. PostgreSQL database
   - Stores processed market data, metadata, and analytics snapshots.
7. Analytics and ML layer
   - Runs trend classification, signal summaries, and exploratory analysis.
8. React frontend
   - Displays dashboards, charts, watchlists, and KPI cards.
9. Live dashboard
   - REST serves snapshots; a backend Upstox V3 feed can forward normalized quotes through the StockSense browser WebSocket.

## Live data requirement

Upstox mode requires an authorized provider feed and valid credentials. Demo mode intentionally uses deterministic synthetic values for development and project demonstration. Demo values are never represented as actual market information; the backend and dashboard identify them as `DEMO DATA`.

With `MARKET_DATA_PROVIDER=demo`, the complete dashboard works without Upstox credentials. With `MARKET_DATA_PROVIDER=upstox`, an authorized access token and exact instrument mappings are required; until configured, market-data endpoints return HTTP 503.

## Provider integration

The `DemoMarketDataProvider` and Upstox v3 adapter both sit behind the provider-neutral `MarketDataService`. Demo mode serves only local deterministic synthetic data. Upstox mode normalizes REST quotes and historical candles into StockSense models; it expects an already-issued access token and does not implement OAuth authorization-code exchange. Configure official instrument keys for each StockSense symbol in `UPSTOX_INSTRUMENT_MAP`.

## Upstox V3 Market Feed

The browser connection at `/ws/market` is a StockSense JSON protocol. It is separate from the backend's authenticated connection to Upstox. The backend keeps the access token private, requests a one-use WebSocket URL from `/v3/feed/market-data-feed/authorize`, sends the V3 subscription envelope as a binary frame, decodes Upstox Protobuf frames, and broadcasts only normalized StockSense quote models.

For Upstox mode, required backend settings are `MARKET_DATA_PROVIDER=upstox`, `UPSTOX_ACCESS_TOKEN`, and `UPSTOX_INSTRUMENT_MAP`. Keep credentials in the project-root `.env`; never add tokens to frontend variables or responses. The instrument map must map each StockSense symbol to its exact Upstox `EXCHANGE|instrument` key. The stream currently requests the `ltpc` mode; it does not treat last-trade quantity as total traded volume.

`UPSTOX_INSTRUMENT_MAP` is a JSON object in `.env`. Use this placeholder shape and replace both values with your internal symbol and the corresponding official key from Upstox; it is not a usable instrument mapping:

```dotenv
UPSTOX_INSTRUMENT_MAP={"YOUR_INTERNAL_SYMBOL":"EXCHANGE|OFFICIAL_INSTRUMENT_KEY"}
```

Demo mode needs no Upstox token or network connection. It uses fixed synthetic baselines and a bounded, repeatable demo-update sequence; its websocket state and quotes are marked `DEMO DATA`. In Upstox mode, without an access token, streaming subscriptions remain unavailable and no upstream connection is attempted. The adapter uses the official V3 Protobuf schema checked into `backend/app/providers/upstox_market_data_feed.proto`; fixture tests validate decoding and broadcast behavior offline. No live authorization, entitlement, redirect, or market tick has been verified in this environment.

When Upstox access is available, verify using a valid backend-only token and confirmed instrument mappings: start the backend and dashboard during an eligible market session, confirm authorization and the one-use redirect connection, check LTPC snapshots/updates for mapped instruments, exercise reconnect behavior, and confirm no token or authorized URL appears in browser messages or logs. Do not use sample or simulated prices for this verification.

## API endpoints

The project now includes provider-backed market endpoints:

- GET /api/market/quote/{symbol}
- GET /api/market/historical/{symbol}
- GET /api/market/index/{symbol}
- GET /api/market/status
- GET /api/market/search?query={text}
- GET /api/market/movers
- GET /api/market/activity

If the provider is not configured, each endpoint returns a clear explanation that configuration is required.

<img width="1536" height="1024" alt="StockSense Market News Dashboard" src="https://github.com/user-attachments/assets/82eb5071-5545-4985-92d7-e87410294057" />


## Folder structure

StockSense/
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── backend/
│   ├── app/
│   ├── requirements.txt
│   └── .env.example (optional if kept at root)
├── data/
├── ml/
├── database/
├── docs/
├── tests/
├── .gitignore
├── .env.example
├── README.md
└── ...

## Environment variables

Copy .env.example to .env and fill in values as needed.

Example:

```bash
cp .env.example .env
```

Set `MARKET_DATA_PROVIDER=demo` for the local synthetic demonstration, or `MARKET_DATA_PROVIDER=upstox` for authorized provider data. Restart the backend after changing this setting. Environment values used by the backend:

- MARKET_DATA_PROVIDER
- MARKET_DATA_BASE_URL
- UPSTOX_ACCESS_TOKEN
- UPSTOX_INSTRUMENT_MAP
- UPSTOX_CLIENT_ID and UPSTOX_CLIENT_SECRET (reserved; token exchange is not implemented)
- DATABASE_URL
- BACKEND_HOST
- BACKEND_PORT
- FRONTEND_PORT

Important: do not commit real secrets or credentials.

## Installation

### 1. Create Python virtual environment

```bash
cd StockSense
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 2. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd ../frontend
npm install
```

## Running the app

### Start backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Start frontend

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

## Testing the health endpoint

Open:

```text
http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "StockSense API"
}
```

## Current project status

The provider-neutral REST API and dashboard support configuration-selected demo and Upstox providers. Demo mode runs without Upstox credentials and labels all synthetic snapshots and controlled WebSocket updates. Upstox V3 REST and streaming paths remain available for authorized integration; real feed access requires valid credentials and official instrument mappings. Demo data is never actual market information.
