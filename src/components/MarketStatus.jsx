export function MarketStatus({ status, timestamp, sourceLabel }) {
  const normalized = (status || 'DATA UNAVAILABLE').toUpperCase();
  const badgeClass = `market-status__badge market-status__badge--${normalized.replace(/\s+/g, '-').toLowerCase() || 'unavailable'}`;

  return (
    <section className="panel market-status">
      <div className="panel__header">
        <h2>Market Status</h2>
      </div>
      <div className="market-status__content">
        <span className={badgeClass}>{normalized}</span>
        <div className="market-status__meta">
          <p>{timestamp || 'Waiting for market data'}</p>
          <small>{sourceLabel || 'Backend status'}</small>
        </div>
      </div>
    </section>
  );
}
