import SeverityBadge from "./SeverityBadge.jsx";

function formatCategory(value) {
  return (value || "other").replace(/_/g, " ");
}

export default function AlertsPanel({ alerts = [], onSelect }) {
  return (
    <aside className="panel alerts-panel">
      <div className="panel-header">
        <h2>Active Alerts</h2>
        <span className="alert-count">{alerts.length}</span>
      </div>
      <div className="alerts-list">
        {!alerts.length ? (
          <p className="panel-hint">No high-severity alerts (60+).</p>
        ) : (
          alerts.slice(0, 25).map((alert) => (
            <button
              type="button"
              key={alert.event_id}
              className="alert-item"
              onClick={() => onSelect(alert.event_id)}
            >
              <h4>{alert.title}</h4>
              <div className="alert-meta">
                <SeverityBadge score={alert.severity_score} />
                <span className="category-pill">{formatCategory(alert.event_category)}</span>
                <span className="category-pill">{alert.geo_country || "Global"}</span>
                <span className={`category-pill status-${(alert.status || "detected").toLowerCase()}`}>
                  {formatCategory(alert.status || "detected")}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
