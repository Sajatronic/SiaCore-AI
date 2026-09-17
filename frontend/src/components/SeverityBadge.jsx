export default function SeverityBadge({ score }) {
  const value = Number(score) || 0;
  let level = "low";
  if (value >= 75) level = "critical";
  else if (value >= 60) level = "high";
  else if (value >= 40) level = "medium";

  return (
    <span className={`badge ${level}`}>
      {Math.round(value)}
    </span>
  );
}
