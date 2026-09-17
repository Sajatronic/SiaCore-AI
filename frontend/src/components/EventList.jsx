import SeverityBadge from "./SeverityBadge.jsx";
import ComponentList from "./ComponentList.jsx";

function formatCategory(value) {
  return (value || "other").replace(/_/g, " ");
}

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

export default function EventList({ events, onSelect, filters, onFilterChange }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Risk Events</h2>
        <div className="filters">
          <input
            type="search"
            placeholder="Search events..."
            value={filters.search}
            onChange={(e) => onFilterChange({ search: e.target.value })}
          />
          <select
            value={filters.category}
            onChange={(e) => onFilterChange({ category: e.target.value })}
          >
            <option value="">All categories</option>
            <option value="logistics_disruption">Logistics disruption</option>
            <option value="geopolitical_event">Geopolitical</option>
            <option value="natural_disaster">Natural disaster</option>
            <option value="factory_shutdown">Factory shutdown</option>
            <option value="export_sanction">Export sanction</option>
            <option value="labor_action">Labor action</option>
            <option value="financial_distress">Financial distress</option>
            <option value="energy_disruption">Energy disruption</option>
            <option value="other">Other</option>
          </select>
          <select
            value={filters.min_severity}
            onChange={(e) => onFilterChange({ min_severity: e.target.value })}
          >
            <option value="">Any severity</option>
            <option value="40">40+ medium</option>
            <option value="60">60+ high</option>
            <option value="75">75+ critical</option>
          </select>
        </div>
      </div>

      {!events?.length ? (
        <div className="empty-state">No events match your filters.</div>
      ) : (
        <table className="event-table">
          <thead>
            <tr>
              <th>Event</th>
              <th>Severity</th>
              <th>Category</th>
              <th>Location</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.event_id} onClick={() => onSelect(event.event_id)}>
                <td>
                  <div className="event-title">{event.title}</div>
                  <div className="event-summary">{event.summary}</div>
                  <SupplyChainFooter event={event} />
                </td>
                <td>
                  <SeverityBadge score={event.severity_score} />
                </td>
                <td>
                  <span className="category-pill">{formatCategory(event.event_category)}</span>
                </td>
                <td>{event.geo_country || event.geo_region || "—"}</td>
                <td>{Math.round((event.overall_confidence || 0) * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
