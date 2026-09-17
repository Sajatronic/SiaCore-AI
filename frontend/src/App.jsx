import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchAlerts, fetchEvent, fetchEvents, fetchGeo, fetchMeta, fetchSummary } from "./api.js";
import AlertsPanel from "./components/AlertsPanel.jsx";
import EventDetail from "./components/EventDetail.jsx";
import EventList from "./components/EventList.jsx";
import GeoMap from "./components/GeoMap.jsx";
import Header from "./components/Header.jsx";
import StatsBar from "./components/StatsBar.jsx";

export default function App() {
  const [meta, setMeta] = useState(null);
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [geoPoints, setGeoPoints] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({
    search: "",
    category: "",
    min_severity: "",
  });

  const queryParams = useMemo(
    () => ({
      limit: 100,
      search: filters.search || undefined,
      category: filters.category || undefined,
      min_severity: filters.min_severity || undefined,
    }),
    [filters]
  );

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [metaData, summaryData, eventsData, geoData, alertsData] = await Promise.all([
        fetchMeta(),
        fetchSummary(),
        fetchEvents(queryParams),
        fetchGeo(),
        fetchAlerts(),
      ]);
      setMeta(metaData);
      setSummary(summaryData);
      setEvents(eventsData.items || []);
      setGeoPoints(geoData.points || []);
      setAlerts(alertsData.items || []);
    } catch (err) {
      setError(err.message || "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [queryParams]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const handleSelectEvent = async (eventId) => {
    try {
      const detail = await fetchEvent(eventId);
      setSelectedEvent(detail);
    } catch (err) {
      setError(err.message || "Failed to load event detail");
    }
  };

  const handleFilterChange = (patch) => {
    setFilters((current) => ({ ...current, ...patch }));
  };

  const visibleEventIds = useMemo(
    () => new Set(events.map((event) => event.event_id)),
    [events]
  );

  const filteredGeoPoints = useMemo(
    () => geoPoints.filter((point) => visibleEventIds.has(point.event_id)),
    [geoPoints, visibleEventIds]
  );

  const filteredAlerts = useMemo(
    () => alerts.filter((alert) => visibleEventIds.has(alert.event_id)),
    [alerts, visibleEventIds]
  );

  if (loading && !events.length) {
    return <div className="app-shell loading">Loading SiaEye intelligence...</div>;
  }

  return (
    <div className="app-shell">
      <Header meta={meta} />
      {error && <div className="error">{error}</div>}
      <StatsBar summary={summary} />
      <div className="intel-grid">
        <section className="panel map-panel">
          <div className="panel-header">
            <h2>Geo Intelligence</h2>
          </div>
          <GeoMap points={filteredGeoPoints} onSelectEvent={handleSelectEvent} />
        </section>
        <AlertsPanel alerts={filteredAlerts} onSelect={handleSelectEvent} />
      </div>
      <EventList
        events={events}
        filters={filters}
        onFilterChange={handleFilterChange}
        onSelect={handleSelectEvent}
      />
      {selectedEvent && (
        <EventDetail event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}
      <p className="footer-note">
        SiaEye by SiaCore — Detect. Assess. Mitigate. Stay resilient.
      </p>
    </div>
  );
}
