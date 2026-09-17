async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

const state = {
  map: null,
  mapMarkers: [],
  geoPoints: [],
  alerts: [],
};

function severityClass(score) {
  if (score >= 75) return "high";
  if (score >= 40) return "med";
  return "low";
}

function markerColor(score) {
  if (score >= 75) return "#a78bfa";
  if (score >= 40) return "#60a5fa";
  return "#2dd4bf";
}

function formatCategory(value) {
  return (value || "other").replace(/_/g, " ");
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function componentBulletRow(label, names) {
  if (!names?.length) return "";
  const items = names
    .map((name) => `<li class="component-bullet">${escapeHtml(name)}</li>`)
    .join("");
  return `<div class="entity-row entity-row-bullets">
    <span class="entity-label">${escapeHtml(label)}</span>
    <ul class="component-list">${items}</ul>
  </div>`;
}

function entityRow(label, names, options = {}) {
  if (!names?.length) return "";
  if (options.bullets) {
    return componentBulletRow(label, names);
  }
  return `<div class="entity-row">
    <span class="entity-label">${escapeHtml(label)}</span>
    ${names.map((name) => `<span class="pill entity">${escapeHtml(name)}</span>`).join("")}
  </div>`;
}

function linkNamesFromSection(links, key) {
  return (links?.[key] || [])
    .map((entry) => entry?.name || entry?.id || "")
    .filter(Boolean);
}

function entityNamesFromEvent(event, key) {
  const fromList = event[key];
  if (Array.isArray(fromList) && fromList.length && typeof fromList[0] === "string") {
    return fromList;
  }
  return (event[key] || [])
    .map((item) => item?.canonical_name || item?.canonical_id || "")
    .filter(Boolean);
}

function supplyChainSections(event) {
  const links = event.supply_chain_links;
  if (links) {
    return [
      ["Components", linkNamesFromSection(links, "components")],
      ["Distributors", linkNamesFromSection(links, "distributors")],
      ["Affected Manufacturers", linkNamesFromSection(links, "affected_manufacturers")],
      ["Locations", linkNamesFromSection(links, "locations")],
    ];
  }
  const affectedManufacturers = [
    ...entityNamesFromEvent(event, "linked_manufacturers"),
    ...(event.affected_manufacturers || []),
  ].filter((name, index, all) => name && all.indexOf(name) === index);
  return [
    ["Components", entityNamesFromEvent(event, "linked_components")],
    ["Distributors", entityNamesFromEvent(event, "linked_suppliers")],
    ["Affected Manufacturers", affectedManufacturers],
    ["Locations", entityNamesFromEvent(event, "linked_locations")],
  ];
}

function supplyChainFooter(event) {
  const rows = supplyChainSections(event)
    .map(([label, names]) => entityRow(label, names, { bullets: label === "Components" }))
    .join("");
  if (!rows) return "";
  return `<div class="entity-footer">${rows}</div>`;
}

function renderStats(summary) {
  document.getElementById("stats").innerHTML = [
    ["Events", summary.total_events],
    ["Avg Severity", summary.avg_severity],
    ["Peak Severity", summary.max_severity],
    ["AI Analysis", summary.with_analysis],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat"><div class="label">${label}</div><div class="value">${value}</div></div>`
    )
    .join("");
}

function renderEvents(items) {
  const root = document.getElementById("events");
  if (!items.length) {
    root.innerHTML = "<div class='event'><p>No events found.</p></div>";
    syncIntelPanels(items);
    return;
  }
  root.innerHTML = items
    .map(
      (e) => `<article class="event" data-id="${e.event_id}">
        <h3>${escapeHtml(e.title)}</h3>
        <p>${escapeHtml(e.summary || "")}</p>
        <div class="row">
          <span class="badge ${severityClass(e.severity_score)}">${Math.round(e.severity_score)}</span>
          <span class="pill">${escapeHtml((e.event_category || "").replace(/_/g, " "))}</span>
          <span class="pill">${escapeHtml(e.geo_country || "Global")}</span>
          ${e.has_risk_analysis ? '<span class="pill ai">AI analysis</span>' : ""}
        </div>
        ${supplyChainFooter(e)}
      </article>`
    )
    .join("");
  root.querySelectorAll(".event").forEach((node) => {
    node.addEventListener("click", () => openDetail(node.dataset.id));
  });
  syncIntelPanels(items);
}

function renderAlerts(items) {
  const root = document.getElementById("alerts");
  const countEl = document.getElementById("alert-count");
  if (!root || !countEl) return;
  countEl.textContent = String(items.length);
  if (!items.length) {
    root.innerHTML = '<p class="panel-hint" style="padding:.75rem">No high-severity alerts (60+).</p>';
    return;
  }
  root.innerHTML = items
    .slice(0, 25)
    .map(
      (alert) => `<div class="alert-item" data-id="${alert.event_id}">
        <h4>${escapeHtml(alert.title)}</h4>
        <div class="alert-meta">
          <span class="badge ${severityClass(alert.severity_score)}">${Math.round(alert.severity_score)}</span>
          <span class="pill">${escapeHtml(formatCategory(alert.event_category))}</span>
          <span class="pill">${escapeHtml(alert.geo_country || "Global")}</span>
        </div>
      </div>`
    )
    .join("");
  root.querySelectorAll(".alert-item").forEach((node) => {
    node.addEventListener("click", () => openDetail(node.dataset.id));
  });
}

function clearMapMarkers() {
  state.mapMarkers.forEach((marker) => marker.remove());
  state.mapMarkers = [];
}

function renderGeoMap(points) {
  const container = document.getElementById("geo-map");
  const hint = document.getElementById("map-hint");
  if (!container) return;

  clearMapMarkers();

  if (!points.length) {
    if (state.map) {
      state.map.remove();
      state.map = null;
    }
    container.className = "geo-map-empty";
    container.innerHTML = "No geocoded events in the current view.";
    if (hint) hint.textContent = "0 points";
    return;
  }

  container.className = "geo-map";
  container.innerHTML = "";
  if (hint) hint.textContent = `${points.length} point${points.length === 1 ? "" : "s"}`;

  if (typeof L === "undefined") {
    container.className = "geo-map-empty";
    container.textContent = "Map library failed to load.";
    return;
  }

  if (!state.map) {
    state.map = L.map(container, { scrollWheelZoom: false }).setView([20, 0], 2);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; OSM &copy; CARTO',
      subdomains: "abcd",
      maxZoom: 19,
    }).addTo(state.map);
  } else {
    state.map.invalidateSize();
  }

  const bounds = [];
  points.forEach((point) => {
    const lat = Number(point.latitude);
    const lon = Number(point.longitude);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;
    bounds.push([lat, lon]);
    const score = Number(point.severity_score || 0);
    const marker = L.circleMarker([lat, lon], {
      radius: score >= 75 ? 9 : score >= 40 ? 7 : 5,
      color: markerColor(score),
      fillColor: markerColor(score),
      fillOpacity: 0.85,
      weight: 1,
    }).addTo(state.map);
    marker.bindPopup(
      `<strong>${escapeHtml(point.title || "Event")}</strong><br/>
       Severity: ${Math.round(score)}<br/>
       ${escapeHtml(formatCategory(point.event_category))}`
    );
    marker.on("click", () => openDetail(point.event_id));
    state.mapMarkers.push(marker);
  });

  if (bounds.length === 1) {
    state.map.setView(bounds[0], 5);
  } else if (bounds.length > 1) {
    state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 6 });
  }
}

function syncIntelPanels(visibleEvents) {
  const visibleIds = new Set((visibleEvents || []).map((event) => event.event_id));
  const hasFilter = visibleIds.size < allItems.length;
  const geoPoints = hasFilter
    ? state.geoPoints.filter((point) => visibleIds.has(point.event_id))
    : state.geoPoints;
  const alertItems = hasFilter
    ? state.alerts.filter((alert) => visibleIds.has(alert.event_id))
    : state.alerts;
  renderGeoMap(geoPoints);
  renderAlerts(alertItems);
}

async function openDetail(eventId) {
  const event = await api(`/api/events/${eventId}`);
  const analysis = event.risk_analysis;
  const body = document.getElementById("detail-body");
  body.innerHTML = `
    <h2>${escapeHtml(event.title)}</h2>
    <p class="detail-summary">${escapeHtml(event.summary || "")}</p>
    ${
      analysis && !analysis.skipped
        ? `<h3>Executive Summary</h3><p>${escapeHtml(analysis.executive_summary || "")}</p>
           <h3>Business Impact</h3><p>${escapeHtml(analysis.business_impact || "")}</p>`
        : ""
    }
    ${supplyChainFooter(event)}
  `;
  document.getElementById("detail").showModal();
}

let allItems = [];

async function boot() {
  const [meta, summary, events, geo, alerts] = await Promise.all([
    api("/api/meta"),
    api("/api/stats/summary"),
    api("/api/events?limit=100"),
    api("/api/stats/geo"),
    api("/api/alerts"),
  ]);
  document.getElementById("tagline").textContent = meta.tagline;
  document.getElementById("meta").innerHTML = `Pipeline v${meta.pipeline_version}<br/>Source: ${meta.backend}`;
  renderStats(summary);
  allItems = events.items || [];
  state.geoPoints = geo.points || [];
  state.alerts = alerts.items || [];
  renderEvents(allItems);

  document.getElementById("search").addEventListener("input", (ev) => {
    const q = ev.target.value.toLowerCase();
    const filtered = allItems.filter((e) => {
      const sections = supplyChainSections(e);
      const linked = sections.flatMap(([, names]) => names).join(" ");
      return `${e.title} ${e.summary} ${e.geo_country} ${linked}`.toLowerCase().includes(q);
    });
    renderEvents(filtered);
  });
  document.getElementById("close-detail").addEventListener("click", () => {
    document.getElementById("detail").close();
  });
}

boot().catch((err) => {
  document.getElementById("events").innerHTML = `<div class="event"><p>${escapeHtml(err.message)}</p></div>`;
});
