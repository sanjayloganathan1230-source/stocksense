export function EmptyState({ title, message }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">–</div>
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  );
}
