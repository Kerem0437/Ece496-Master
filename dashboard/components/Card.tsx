export default function Card({
  title,
  subtitle,
  children
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  // Simple reusable layout primitive.
  // Why: keeps pages readable and consistent; later you can swap styling without touching content.
  return (
    <section
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 14,
        background: "rgba(255,255,255,0.03)",
        boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
        padding: 14
      }}
    >
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontWeight: 700, letterSpacing: 0.2 }}>{title}</div>
        {subtitle ? <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{subtitle}</div> : null}
      </div>
      {children}
    </section>
  );
}
