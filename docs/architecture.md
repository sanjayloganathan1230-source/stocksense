# StockSense architecture overview

This project uses a layered architecture:

1. Market data provider
   - Configuration selects the local deterministic `DemoMarketDataProvider` or the Upstox adapter.
2. FastAPI backend
   - Accepts requests, orchestrates data ingestion, and exposes APIs.
3. Processing layer
   - Cleans, transforms, and validates data using pandas and NumPy.
4. PostgreSQL database
   - Stores processed market data and analytics records.
5. AI/ML layer
   - Prepares model-ready data and supports educational trend analysis.
6. React frontend
   - Displays dashboard views and market summaries.
7. Provider stream
   - Demo mode emits deterministic synthetic updates; Upstox mode obtains its V3 authorized URL, subscribes using mapped instrument keys, and decodes Protobuf feed frames.
8. Browser dashboard
   - REST provides initial snapshots; normalized quote updates are broadcast through the separate StockSense `/ws/market` JSON WebSocket.

This design keeps data-provider logic isolated from the rest of the system.

Demo mode supplies deterministic synthetic quotes, indexes, candles, movers, activity, and controlled WebSocket demo updates. All demo values are identified as `DEMO DATA` and are not real market information. Upstox mode retains the V3 REST/feed adapters and requires valid backend credentials and official instrument mappings. Its upstream socket, token, and one-use URL remain backend-only. Live authorization and feed behavior require later verification with Upstox access.
