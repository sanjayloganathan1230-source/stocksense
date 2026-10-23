export function IndexCard({ label, value, change, changePercent, status, timestamp }) {
  const formattedValue = value ?? 'Data unavailable';
  const formattedChange = change ?? '—';
  const formattedPercent = changePercent ?? '—';

  return (
    <article className="index-card panel">
      <div className="index-card__top">
        <span className="index-card__label">{label}</span>
        <span className="index-card__status">{status || 'DATA UNAVAILABLE'}</span>
      </div>
      <div className="index-card__value">{formattedValue}</div>
      <div className="index-card__meta">
        <span className="trend trend--neutral">{formattedChange}</span>
        <span className="trend trend--neutral">{formattedPercent}</span>
      </div>
      <small>{timestamp || 'Waiting for market data'}</small>
    </article>
  );
}
