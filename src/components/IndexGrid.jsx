import { IndexCard } from './IndexCard';

export function IndexGrid({ indexes = [] }) {
  return (
    <section className="panel">
      <div className="panel__header">
        <h2>Major Indexes</h2>
      </div>
      <div className="index-grid">
        {indexes.length ? (
          indexes.map((index) => (
            <IndexCard
              key={index.label}
              label={index.label}
              value={index.value}
              change={index.change}
              changePercent={index.changePercent}
              status={index.status}
              timestamp={index.timestamp}
            />
          ))
        ) : (
          <div className="empty-grid">
            <p>Waiting for market data</p>
          </div>
        )}
      </div>
    </section>
  );
}
