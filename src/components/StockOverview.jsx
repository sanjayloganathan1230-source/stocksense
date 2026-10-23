export function StockOverview({ quote, error, loading }) {
  if (loading) {
    return <div className="panel"><div className="panel__header"><h2>Selected Stock</h2></div><div className="loading-state"><div className="spinner" aria-hidden="true" /><span>Loading stock details...</span></div></div>;
  }

  if (error) {
    return <div className="panel"><div className="panel__header"><h2>Selected Stock</h2></div><div className="error-state"><div className="error-state__badge">!</div><h3>Data unavailable</h3><p>{error}</p></div></div>;
  }

  if (!quote) {
    return <div className="panel"><div className="panel__header"><h2>Selected Stock</h2></div><div className="empty-state"><div className="empty-state__icon">–</div><h3>No stock selected</h3><p>Choose a stock to view details.</p></div></div>;
  }

  return (
    <section className="panel stock-overview">
      <div className="panel__header stock-overview__header">
        <div>
          <div className="eyebrow">Selected Stock</div>
          <h2>{quote.symbol}</h2>
        </div>
        <span className="data-source">{quote.market_status || 'DATA UNAVAILABLE'}</span>
      </div>

      <div className="stock-overview__grid">
        <div className="stock-overview__primary">
          <div className="stock-overview__name">{quote.company_name || 'Company not available'}</div>
          <div className="stock-overview__price">₹{quote.last_price ?? 'Data unavailable'}</div>
          <div className="stock-overview__change-row">
            <span className="trend trend--neutral">{quote.change ?? '—'}</span>
            <span className="trend trend--neutral">{quote.change_percent ?? '—'}</span>
          </div>
        </div>

        <div className="stock-overview__stats">
          <div><span>Open</span><strong>₹{quote.open ?? '—'}</strong></div>
          <div><span>High</span><strong>₹{quote.high ?? '—'}</strong></div>
          <div><span>Low</span><strong>₹{quote.low ?? '—'}</strong></div>
          <div><span>Prev Close</span><strong>₹{quote.previous_close ?? '—'}</strong></div>
          <div><span>Volume</span><strong>{quote.volume ?? '—'}</strong></div>
          <div><span>Timestamp</span><strong>{quote.timestamp || 'Waiting for market data'}</strong></div>
          <div><span>Source</span><strong>{quote.data_source || 'StockSense backend'}</strong></div>
          <div><span>Status</span><strong>{quote.market_status || 'DATA UNAVAILABLE'}</strong></div>
        </div>
      </div>
    </section>
  );
}
