import SeverityBadge from "./SeverityBadge.jsx";
import ComponentList from "./ComponentList.jsx";

function entityNames(items) {
  if (!items?.length) return [];
  if (typeof items[0] === "string") return items;
  return items.map((item) => item?.name || item?.canonical_name || item?.id || item?.canonical_id).filter(Boolean);
}

function sectionsFromEvent(event) {
  const links = event.supply_chain_links;
  if (links) {
    return [
      ["Components", entityNames(links.components)],
      ["Distributors", entityNames(links.distributors)],
      ["Affected Manufacturers", entityNames(links.affected_manufacturers)],
      ["Locations", entityNames(links.locations)],
    ];
  }
  const affectedManufacturers = [
    ...entityNames(event.linked_manufacturers),
    ...(event.affected_manufacturers || []),
  ].filter((name, index, all) => name && all.indexOf(name) === index);
  return [
    ["Components", entityNames(event.linked_components)],
    ["Distributors", entityNames(event.linked_suppliers)],
    ["Affected Manufacturers", affectedManufacturers],
    ["Locations", entityNames(event.linked_locations)],
  ];
}

function SupplyChainFooter({ event }) {
  const sections = sectionsFromEvent(event);
  const rows = sections.filter(([, names]) => names.length);
  if (!rows.length) return null;

  return (
    <div className="entity-footer">
      {rows.map(([label, names]) => (
        <div
          key={label}
          className={`entity-row${label === "Components" ? " entity-row-bullets" : ""}`}
        >
          <span className="entity-label">{label}</span>
          {label === "Components" ? (
            <ComponentList names={names} />
          ) : (
            names.map((name) => (
              <span key={name} className="category-pill entity-pill">
                {name}
              </span>
            ))
          )}
        </div>
      ))}
    </div>
  );
}

export default function EventDetail({ event, onClose }) {
  if (!event) return null;

  const analysis = event.risk_analysis;

  return (
    <div className="detail-overlay" onClick={onClose}>
      <aside className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="close-btn" onClick={onClose}>
          Close
        </button>
        <h2>{event.title}</h2>
        <div className="detail-meta">
          <SeverityBadge score={event.severity_score} />
          <span className={`category-pill status-${(event.status || "detected").toLowerCase()}`}>
            {(event.status || "detected").replace(/_/g, " ")}
          </span>
          <span className="category-pill">{(event.event_category || "").replace(/_/g, " ")}</span>
          <span className="category-pill">{event.geo_country || "Global"}</span>
        </div>

        <p className="detail-summary">{event.summary}</p>

        {analysis && !analysis.skipped && (
          <>
            <div className="detail-section">
              <h3>Executive Summary</h3>
              <p>{analysis.executive_summary}</p>
            </div>
            <div className="detail-section">
              <h3>Business Impact</h3>
              <p>{analysis.business_impact}</p>
            </div>
          </>
        )}

        <SupplyChainFooter event={event} />
      </aside>
    </div>
  );
}
