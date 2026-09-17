export default function Header({ meta }) {
  return (
    <header className="header">
      <div className="brand">
        <img src="/logo.svg" alt="SiaCore" className="brand-logo" />
        <div className="brand-text">
          <div className="product">SiaEye</div>
          <h1>
            Sia<span className="core">Core</span>
          </h1>
          <p className="tagline">
            {meta?.tagline || "Ancient Wisdom. Modern Intelligence."}
          </p>
        </div>
      </div>
      <div className="header-meta">
        <div>Supply Chain Intelligence</div>
        <div>Pipeline v{meta?.pipeline_version || "—"}</div>
        <div>Source: {meta?.backend || "local"}</div>
      </div>
    </header>
  );
}
