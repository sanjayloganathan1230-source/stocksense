export function MarketMovers({ gainers = [], losers = [], dataMode }) {
  return (
    <div className="movers-grid">
      <section className="panel">
        <div className="panel__header"><h2>Top Gainers</h2>{dataMode === 'demo' && <small>DEMO DATA</small>}</div>
        {gainers.length ? (
          <ul className="mover-list">
            {gainers.map((item) => (
              <li key={item.symbol || item.name || 'gainer'}>
                <span>{item.symbol || '—'}</span>
                <strong>{item.change || '—'}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty-state compact"><div className="empty-state__icon">–</div><p>Waiting for market data</p></div>
        )}
      </section>

      <section className="panel">
        <div className="panel__header"><h2>Top Losers</h2>{dataMode === 'demo' && <small>DEMO DATA</small>}</div>
        {losers.length ? (
          <ul className="mover-list">
            {losers.map((item) => (
              <li key={item.symbol || item.name || 'loser'}>
                <span>{item.symbol || '—'}</span>
                <strong>{item.change || '—'}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <div className="empty-state compact"><div className="empty-state__icon">–</div><p>Waiting for market data</p></div>
        )}
      </section>
    </div>
  );
}
