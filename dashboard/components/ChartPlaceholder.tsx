import Card from "./Card";

type Point = { x: number; y: number };

function evenlySample(points: Point[], limit = 240): Point[] {
  if (points.length <= limit) return points;
  const out: Point[] = [];
  for (let i = 0; i < limit; i += 1) {
    const idx = Math.round((i * (points.length - 1)) / Math.max(1, limit - 1));
    out.push(points[idx]);
  }
  return out;
}

export default function ChartPlaceholder({
  title,
  unit,
  points
}: {
  title: string;
  unit: string;
  points: Point[];
}) {
  // Lightweight SVG chart placeholder (no heavy chart libs yet).
  // Why: keeps T5 demo visual and real-data-ready without adding complexity.
  // Later: swap this component for Recharts/Chart.js and keep callers the same.

  const width = 980;
  const height = 220;
  const padding = 20;

  const safePoints = evenlySample(points, 240); // keep the full time range visible
  const xs = safePoints.map(p => p.x);
  const ys = safePoints.map(p => p.y);

  const minX = xs.length ? Math.min(...xs) : 0;
  const maxX = xs.length ? Math.max(...xs) : 1;
  const minY = ys.length ? Math.min(...ys) : 0;
  const maxY = ys.length ? Math.max(...ys) : 1;

  const scaleX = (x: number) => {
    if (maxX === minX) return padding;
    return padding + ((x - minX) / (maxX - minX)) * (width - padding * 2);
  };

  const scaleY = (y: number) => {
    if (maxY === minY) return height / 2;
    // invert y for svg
    return height - padding - ((y - minY) / (maxY - minY)) * (height - padding * 2);
  };

  const polyline = safePoints
    .map(p => `${scaleX(p.x).toFixed(1)},${scaleY(p.y).toFixed(1)}`)
    .join(" ");

  return (
    <Card
      title={title}
      subtitle={`points: ${safePoints.length} • y-range: ${minY.toFixed(3)} to ${maxY.toFixed(3)} ${unit}`}
    >
      <div style={{ overflowX: "auto" }}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{
            borderRadius: 12,
            border: "1px solid rgba(15,23,42,0.12)",
            background: "#ffffff"
          }}
        >
          {/* grid lines */}
          {Array.from({ length: 6 }).map((_, i) => {
            const y = padding + (i * (height - padding * 2)) / 5;
            return (
              <line
                key={i}
                x1={padding}
                y1={y}
                x2={width - padding}
                y2={y}
                stroke="rgba(15,23,42,0.08)"
              />
            );
          })}

          {/* main line */}
          <polyline
            fill="none"
            stroke="rgba(96,165,250,0.95)"
            strokeWidth="2"
            points={polyline}
          />

          {/* axes labels (minimal) */}
          <text x={padding} y={14} fontSize="12" fill="rgba(71,85,105,0.9)">
            y: value ({unit})
          </text>
          <text x={padding} y={height - 6} fontSize="12" fill="rgba(71,85,105,0.9)">
            x: time_offset_seconds (min {minX} / max {maxX})
          </text>
        </svg>
      </div>

      {safePoints.length === 0 ? (
        <div className="small" style={{ marginTop: 8 }}>
          No data points available (mock).
        </div>
      ) : (
        <div className="small" style={{ marginTop: 8 }}>
          Preview: first 5 points →{" "}
          <span className="mono">
            {safePoints.slice(0, 5).map(p => `(${p.x},${p.y})`).join(" ")}
          </span>
        </div>
      )}
    </Card>
  );
}
