export function Header({ dataMode }) {
  const isDemo = dataMode === 'demo';

  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">Indian Market Analytics</div>
        <h1>StockSense</h1>
      </div>
      <div className={`topbar__status${isDemo ? ' topbar__status--demo' : ''}`}>
        <span className={`dot${isDemo ? ' dot--demo' : ' dot--live'}`} aria-hidden="true" />
        <span>
          <strong>{isDemo ? 'DEMO DATA' : 'Backend ready'}</strong>
          {isDemo && <small>Demo/synthetic market data — not real-time market data</small>}
        </span>
      </div>
    </header>
  );
}
