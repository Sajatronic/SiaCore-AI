const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`API error ${response.status}`);
  }
  return response.json();
}

export function fetchMeta() {
  return request("/api/meta");
}

export function fetchSummary() {
  return request("/api/stats/summary");
}

export function fetchEvents(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request(`/api/events${suffix}`);
}

export function fetchEvent(eventId) {
  return request(`/api/events/${eventId}`);
}

export function fetchGeo(minSeverity = 0) {
  return request(`/api/stats/geo?min_severity=${minSeverity}`);
}

export function fetchAlerts() {
  return request("/api/alerts");
}

export function fetchRuns() {
  return request("/api/runs");
}
