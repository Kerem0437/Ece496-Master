import type { IntegrityStatus, MLFlag } from "@/lib/types";

// A small, stable component for status visualization.
// Why: ensures we display statuses consistently across list + detail pages.
// Later: you can centralize threshold logic here without rewriting pages.

export default function StatusPill({
  kind,
  value
}: {
  kind: "integrity";
  value: IntegrityStatus;
} | {
  kind: "ml";
  value: MLFlag;
}) {
  const { bg, border, label } = computeStyle(kind, value as any);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px",
        borderRadius: 999,
        border: `1px solid ${border}`,
        background: bg,
        fontSize: 12,
        color: "#0f172a",
        letterSpacing: 0.2
      }}
      className="mono"
    >
      {label}
    </span>
  );
}

function computeStyle(kind: "integrity" | "ml", value: IntegrityStatus | MLFlag) {
  if (kind === "integrity") {
    if (value === "VALID") return { label: "VALID", bg: "rgba(34,197,94,0.12)", border: "rgba(34,197,94,0.35)" };
    if (value === "VERIFIED") return { label: "VERIFIED", bg: "rgba(34,197,94,0.12)", border: "rgba(34,197,94,0.35)" };
    if (value === "INVALID") return { label: "INVALID", bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.35)" };
    return { label: "UNKNOWN", bg: "rgba(148,163,184,0.10)", border: "rgba(148,163,184,0.28)" };
  }

  // ML flags
  if (value === "NORMAL") return { label: "NORMAL", bg: "rgba(34,197,94,0.12)", border: "rgba(34,197,94,0.35)" };
  if (value === "SUSPICIOUS") return { label: "SUSPICIOUS", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.35)" };
  if (value === "INSUFFICIENT_DATA") return { label: "INSUFFICIENT_DATA", bg: "rgba(147,51,234,0.12)", border: "rgba(147,51,234,0.35)" };
  return { label: "UNKNOWN", bg: "rgba(148,163,184,0.10)", border: "rgba(148,163,184,0.28)" };
}
