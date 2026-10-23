export function LoadingState({ label = 'Loading market data...' }) {
  return (
    <div className="loading-state">
      <div className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
