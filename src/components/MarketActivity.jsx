export function MarketActivity({ activity = null, dataMode }) {
  if (!activity) {
    return (
      <section className="panel">
        <div className="panel__header"><h2>Market Activity</h2>{dataMode === 'demo' && <small>DEMO DATA</small>}</div>
        <div className="empty-state compact">
          <div className="empty-state__icon">–</div>
          <p>Waiting for market activity data</p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel__header"><h2>Market Activity</h2>{dataMode === 'demo' && <small>DEMO DATA</small>}</div>
      <div className="activity-grid">
        <div><span>Volume</span><strong>{activity.volume || 'N/A'}</strong></div>
        <div><span>Active Stocks</span><strong>{activity.activeStocks || 'N/A'}</strong></div>
        <div><span>Advancing</span><strong>{activity.advancing || 'N/A'}</strong></div>
        <div><span>Declining</span><strong>{activity.declining || 'N/A'}</strong></div>
      </div>
    </section>
  );
}
