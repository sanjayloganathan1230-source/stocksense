export function ErrorState({ title = 'Unable to load data', message }) {
  return (
    <div className="error-state">
      <div className="error-state__badge">!</div>
      <h3>{title}</h3>
      <p>{message || 'The backend is not available or the provider is not configured yet.'}</p>
    </div>
  );
}
