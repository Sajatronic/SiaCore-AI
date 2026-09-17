import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

function markerColor(score) {
  if (score >= 75) return "#a78bfa";
  if (score >= 40) return "#60a5fa";
  return "#2dd4bf";
}

export default function GeoMap({ points = [], onSelectEvent }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);

  useEffect(() => {
    if (!containerRef.current || !points.length) {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
      markersRef.current = [];
      return undefined;
    }

    if (!mapRef.current) {
      mapRef.current = L.map(containerRef.current, { scrollWheelZoom: false }).setView([20, 0], 2);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; OSM &copy; CARTO',
        subdomains: "abcd",
        maxZoom: 19,
      }).addTo(mapRef.current);
    }

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

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
      }).addTo(mapRef.current);
      marker.bindPopup(`${point.title || "Event"} · ${Math.round(score)}`);
      marker.on("click", () => onSelectEvent?.(point.event_id));
      markersRef.current.push(marker);
    });

    if (bounds.length === 1) {
      mapRef.current.setView(bounds[0], 5);
    } else if (bounds.length > 1) {
      mapRef.current.fitBounds(bounds, { padding: [24, 24], maxZoom: 6 });
    }

    mapRef.current.invalidateSize();

    return undefined;
  }, [points, onSelectEvent]);

  useEffect(
    () => () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    },
    []
  );

  if (!points.length) {
    return <div className="geo-map-empty">No geocoded events in the current filter set.</div>;
  }

  return (
    <div className="geo-map-wrap">
      <div ref={containerRef} className="geo-map" role="img" aria-label="Event severity map" />
      <span className="panel-hint">{points.length} point{points.length === 1 ? "" : "s"}</span>
    </div>
  );
}
