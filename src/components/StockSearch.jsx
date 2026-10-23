import { useEffect, useState } from 'react';
import { api } from '../services/api';

export function StockSearch({ value, onChange, onSubmit, loading }) {
  const [results, setResults] = useState([]);

  const handleInputChange = (event) => {
    setResults([]);
    onChange(event.target.value);
  };

  useEffect(() => {
    if (!value.trim()) {
      setResults([]);
      return undefined;
    }

    let isCurrent = true;
    const timer = window.setTimeout(async () => {
      try {
        const matches = await api.searchSymbols(value.trim());
        if (isCurrent) {
          setResults(Array.isArray(matches) ? matches : []);
        }
      } catch (error) {
        if (isCurrent) {
          setResults([]);
        }
      }
    }, 150);

    return () => {
      isCurrent = false;
      window.clearTimeout(timer);
    };
  }, [value]);

  return (
    <section className="panel stock-search-panel">
      <div className="panel__header">
        <h2>Stock Search</h2>
      </div>
      <form className="stock-search" onSubmit={onSubmit}>
        <input
          type="text"
          value={value}
          onChange={handleInputChange}
          placeholder="Search Indian stocks..."
          aria-label="Search Indian stocks"
        />
        <button type="submit" disabled={loading || !value.trim()}>
          {loading ? 'Loading...' : 'Search'}
        </button>
      </form>
      {results.length > 0 && !results.some((item) => item.symbol === value.trim().toUpperCase()) && (
        <ul className="search-results" aria-label="Matching demo/provider symbols">
          {results.map((item) => (
            <li key={item.symbol}>
              <button type="button" onClick={() => onSubmit({ preventDefault: () => {} }, item.symbol)}>
                <strong>{item.symbol}</strong><span>{item.company_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="quick-tickers">
        {['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK'].map((symbol) => (
          <button key={symbol} type="button" onClick={() => onSubmit({ preventDefault: () => {} }, symbol)}>
            {symbol}
          </button>
        ))}
      </div>
    </section>
  );
}
