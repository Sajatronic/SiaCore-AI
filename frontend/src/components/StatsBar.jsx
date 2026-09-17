export default function StatsBar({ summary }) {
  if (!summary) return null;

  const categories = Object.entries(summary.categories || {}).slice(0, 3);

  return (
    <section className="stats-grid">
      <div className="stat-card">
        <div className="label">Active Events</div>
        <div className="value gradient">{summary.total_events}</div>
      </div>
      <div className="stat-card">
        <div className="label">Avg Severity</div>
        <div className="value">{summary.avg_severity}</div>
      </div>
      <div className="stat-card">
        <div className="label">Peak Severity</div>
        <div className="value">{summary.max_severity}</div>
      </div>
      <div className="stat-card">
        <div className="label">AI Analysis</div>
        <div className="value">{summary.with_analysis}</div>
      </div>
      <div className="stat-card">
        <div className="label">Top Categories</div>
        <div className="value" style={{ fontSize: "0.95rem", fontWeight: 600 }}>
          {categories.length
            ? categories.map(([name, count]) => `${name.replace(/_/g, " ")} (${count})`).join(" · ")
            : "—"}
        </div>
      </div>
    </section>
  );
}
