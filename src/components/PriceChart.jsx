export function PriceChart({ data = [], range, onRangeChange }) {
  if (!data.length) {
    return (
      <section className="panel price-chart-panel">
        <div className="panel__header price-chart-panel__header">
          <h2>Price Chart</h2>
          <div className="range-switcher">
            {['1D', '1W', '1M', '3M', '6M', '1Y'].map((option) => (
              <button key={option} type="button" className={range === option ? 'active' : ''} onClick={() => onRangeChange(option)}>
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className="empty-state">
          <div className="empty-state__icon">–</div>
          <h3>No historical data available</h3>
          <p>Historical chart data will appear once the backend provides it.</p>
        </div>
      </section>
    );
  }

  const values = data.map((point) => Number(point.close ?? point.value ?? 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const rangeValue = max - min || 1;

  const points = data
    .map((point, index) => {
      const x = (index / Math.max(data.length - 1, 1)) * 100;
      const y = 100 - ((Number(point.close ?? point.value ?? 0) - min) / rangeValue) * 100;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <section className="panel price-chart-panel">
      <div className="panel__header price-chart-panel__header">
        <h2>Price Chart</h2>
        <div className="range-switcher">
          {['1D', '1W', '1M', '3M', '6M', '1Y'].map((option) => (
            <button key={option} type="button" className={range === option ? 'active' : ''} onClick={() => onRangeChange(option)}>
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-shell">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Price chart">
          <defs>
            <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="rgba(81, 170, 255, 0.45)" />
              <stop offset="100%" stopColor="rgba(81, 170, 255, 0.02)" />
            </linearGradient>
          </defs>
          <polyline fill="none" stroke="#57a6ff" strokeWidth="2" points={points} />
          <polygon points={`0,100 ${points} 100,100`} fill="url(#chartFill)" opacity="0.8" />
        </svg>
      </div>

      <div className="chart-meta">
        {data.slice(-4).map((point, index) => (
          <div key={`${point.timestamp || index}`} className="chart-point">
            <span>{point.timestamp ? new Date(point.timestamp).toLocaleDateString() : '—'}</span>
            <strong>₹{Number(point.close ?? point.value ?? 0).toFixed(2)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
