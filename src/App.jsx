import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './services/api';
import { MarketWebSocketClient } from './services/websocket';
import { Header } from './components/Header';
import { MarketStatus } from './components/MarketStatus';
import { IndexGrid } from './components/IndexGrid';
import { StockSearch } from './components/StockSearch';
import { StockOverview } from './components/StockOverview';
import { PriceChart } from './components/PriceChart';
import { MarketMovers } from './components/MarketMovers';
import { MarketActivity } from './components/MarketActivity';
import { ErrorState } from './components/ErrorState';

const INDEX_SYMBOLS = [
  { label: 'NIFTY 50', symbol: 'NIFTY' },
  { label: 'BANK NIFTY', symbol: 'BANKNIFTY' },
  { label: 'SENSEX', symbol: 'SENSEX' },
  { label: 'INDIA VIX', symbol: 'INDIAVIX' },
];

const DEFAULT_INDEXES = INDEX_SYMBOLS.map((item) => ({
  label: item.label,
  value: 'Unavailable',
  change: '—',
  changePercent: '—',
  status: 'UNAVAILABLE',
  timestamp: 'Waiting for market data',
}));

function App() {
  const websocketRef = useRef(null);
  const [search, setSearch] = useState('TCS');
  const [selectedSymbol, setSelectedSymbol] = useState('TCS');
  const selectedSymbolRef = useRef(selectedSymbol);
  selectedSymbolRef.current = selectedSymbol;
  const [systemStatus, setSystemStatus] = useState(null);
  const [marketStatus, setMarketStatus] = useState(null);
  const [indexes, setIndexes] = useState(DEFAULT_INDEXES);
  const [movers, setMovers] = useState({ gainers: [], losers: [] });
  const [marketActivity, setMarketActivity] = useState(null);
  const [selectedQuote, setSelectedQuote] = useState(null);
  const [historicalData, setHistoricalData] = useState([]);
  const [chartRange, setChartRange] = useState('1D');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [wsStatus, setWsStatus] = useState('connecting');

  useEffect(() => {
    let isMounted = true;

    async function loadSystemStatus() {
      try {
        const status = await api.getSystemStatus();
        if (isMounted) {
          setSystemStatus(status);
        }
      } catch (loadError) {
        if (isMounted) {
          setSystemStatus({ status: 'error', detail: 'Backend unavailable' });
        }
      }
    }

    async function loadMarketStatus() {
      try {
        const status = await api.getMarketStatus('NSE');
        if (isMounted) {
          setMarketStatus(status);
        }
      } catch (statusError) {
        if (isMounted) {
          setMarketStatus({ market_status: 'UNAVAILABLE', message: 'Live market data unavailable' });
        }
      }
    }

    async function loadIndexes() {
      try {
        const values = await Promise.all(
          INDEX_SYMBOLS.map(async ({ label, symbol }) => {
            try {
              const indexQuote = await api.getIndexQuote(symbol);
              return {
                label,
                value: typeof indexQuote.value === 'number' ? `₹${indexQuote.value}` : 'Unavailable',
                change: typeof indexQuote.change === 'number' ? `₹${indexQuote.change}` : '—',
                changePercent: typeof indexQuote.change_percent === 'number' ? `${indexQuote.change_percent.toFixed(2)}%` : '—',
                status: indexQuote.market_status || 'UNAVAILABLE',
                timestamp: indexQuote.timestamp ? new Date(indexQuote.timestamp).toLocaleString() : 'Waiting for market data',
              };
            } catch (indexError) {
              return {
                label,
                value: 'Unavailable',
                change: '—',
                changePercent: '—',
                status: 'UNAVAILABLE',
                timestamp: 'Waiting for market data',
              };
            }
          }),
        );

        if (isMounted) {
          setIndexes(values);
        }
      } catch (loadIndexError) {
        if (isMounted) {
          setIndexes(DEFAULT_INDEXES);
        }
      }
    }

    async function loadMoversAndActivity() {
      const [moverData, activityData] = await Promise.allSettled([
        api.getMarketMovers(),
        api.getMarketActivity(),
      ]);
      if (!isMounted) {
        return;
      }
      if (moverData.status === 'fulfilled') {
        setMovers(moverData.value);
      }
      if (activityData.status === 'fulfilled') {
        setMarketActivity(activityData.value);
      }
    }

    loadSystemStatus();
    loadMarketStatus();
    loadIndexes();
    loadMoversAndActivity();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedSymbol) {
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError('');

    async function loadQuote() {
      try {
        const quote = await api.getQuote(selectedSymbol);
        if (isMounted) {
          setSelectedQuote({
            ...quote,
            data_source: systemStatus?.data_mode === 'demo' ? 'Synthetic demo data' : 'StockSense backend',
            market_status: quote.market_status || marketStatus?.market_status || 'DATA UNAVAILABLE',
          });
        }
      } catch (quoteError) {
        if (isMounted) {
          setSelectedQuote(null);
          setError(quoteError.message || 'The backend is not ready for this symbol yet.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    async function loadHistoricalData() {
      try {
        const rangeMap = {
          '1D': '1d',
          '1W': '1w',
          '1M': '1m',
          '3M': '3m',
          '6M': '6m',
          '1Y': '1y',
        };

        const chartRangeValue = rangeMap[chartRange] || '1d';
        const candleData = await api.getHistoricalData(selectedSymbol, chartRangeValue);
        if (isMounted) {
          setHistoricalData(Array.isArray(candleData) ? candleData : []);
        }
      } catch (historyError) {
        if (isMounted) {
          setHistoricalData([]);
        }
      }
    }

    loadQuote();
    loadHistoricalData();

    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, chartRange, marketStatus, systemStatus]);

  useEffect(() => {
    const websocketUrl = 'ws://localhost:8000/ws/market';
    const client = new MarketWebSocketClient(websocketUrl, {
      onOpen: () => websocketRef.current?.subscribe([selectedSymbolRef.current]),
      onClose: () => setWsStatus('disconnected'),
      onError: () => setWsStatus('error'),
      onMessage: (message) => {
        if (message?.status === 'subscribed') {
          setWsStatus('subscribed');
        } else if (message?.status === 'demo') {
          setWsStatus('demo');
        } else if (message?.status === 'unavailable') {
          setWsStatus('unavailable');
        } else if (message?.status === 'error') {
          setWsStatus('error');
        }

        if (
          message &&
          typeof message.symbol === 'string' &&
          typeof message.last_price === 'number' &&
          Number.isFinite(message.last_price) &&
          message.last_price > 0
        ) {
          setSelectedQuote((current) => (
            current && current.symbol === message.symbol
              ? {
                  ...current,
                  last_price: message.last_price,
                  change: message.change ?? current.change,
                  change_percent: message.change_percent ?? current.change_percent,
                  volume: message.volume ?? current.volume,
                  timestamp: message.timestamp || current.timestamp,
                  market_status: message.market_status || current.market_status,
                }
              : current
          ));
        }
      },
    });

    websocketRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
    };
  }, []);

  useEffect(() => {
    if (websocketRef.current?.isConnected && selectedSymbol) {
      websocketRef.current.subscribe([selectedSymbol]);
    }
  }, [selectedSymbol]);

  const marketSummary = useMemo(() => {
    if (systemStatus?.data_mode === 'demo') {
      return 'DEMO DATA';
    }
    if (marketStatus?.market_status) {
      return marketStatus.market_status.toUpperCase();
    }
    return systemStatus?.stream_status === 'connected' ? 'LIVE' : 'UNAVAILABLE';
  }, [marketStatus, systemStatus]);

  const handleSearchSubmit = (event, symbolOverride) => {
    event.preventDefault();
    const symbol = (symbolOverride || search || '').trim().toUpperCase();
    if (!symbol) {
      return;
    }
    setSelectedSymbol(symbol);
    setSearch(symbol);
  };

  const indexCards = indexes.length ? indexes : DEFAULT_INDEXES;

  if (!systemStatus && !marketStatus) {
    return (
      <div className="app-shell app-shell--centered">
        <div className="loading-state"><div className="spinner" aria-hidden="true" /><span>Starting StockSense dashboard...</span></div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="dashboard">
        <Header dataMode={systemStatus?.data_mode} />

        <MarketStatus
          status={marketSummary}
          timestamp={marketStatus?.timestamp ? new Date(marketStatus.timestamp).toLocaleString() : 'Waiting for market data'}
          sourceLabel={systemStatus?.data_mode === 'demo'
            ? 'Demo/synthetic market data — not real-time market data'
            : systemStatus?.market_data_provider ? `Provider: ${systemStatus.market_data_provider}` : 'Provider status pending'}
        />

        <IndexGrid indexes={indexCards} />

        <div className="content-grid">
          <StockSearch value={search} onChange={setSearch} onSubmit={handleSearchSubmit} loading={loading} />
          <div className="panel websocket-panel">
            <div className="panel__header">
              <h2>{systemStatus?.data_mode === 'demo' ? 'Demo Feed' : 'Live Feed'}</h2>
            </div>
            <div className="ws-status">
              <span className={`status-pill status-pill--${wsStatus}`}>{wsStatus.toUpperCase()}</span>
              <small>
                {wsStatus === 'demo'
                  ? 'Synthetic demo updates — not real-time market data'
                  : wsStatus === 'unavailable'
                  ? 'Live market-data streaming is not configured'
                  : wsStatus === 'subscribed'
                    ? 'Provider stream subscribed'
                    : wsStatus === 'error' || wsStatus === 'disconnected'
                      ? 'WebSocket unavailable'
                      : systemStatus?.data_mode === 'demo'
                        ? 'Starting synthetic demo updates'
                        : 'Checking live-feed availability'}
              </small>
            </div>
          </div>
        </div>

        <div className="detail-grid">
          <StockOverview quote={selectedQuote} error={error} loading={loading} />
          <PriceChart data={historicalData} range={chartRange} onRangeChange={setChartRange} />
        </div>

        <div className="bottom-grid">
          <MarketMovers gainers={movers.gainers || []} losers={movers.losers || []} dataMode={systemStatus?.data_mode} />
          <MarketActivity activity={marketActivity} dataMode={systemStatus?.data_mode} />
        </div>

        {error && <ErrorState title="Market data unavailable" message={error} />}
      </div>
    </div>
  );
}

export default App;
