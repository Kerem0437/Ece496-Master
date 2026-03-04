import Link from "next/link";
import Card from "@/components/Card";

export default function VariablesPage() {
  // Small, in-app pointer to docs.
  // Why: supervisors/teammates can discover the variables quickly from the UI.
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <h1 className="h1">Variables</h1>
      <p className="sub">
        Master variable names are documented in <span className="mono">docs/VARIABLES.md</span>.
        This page is a quick pointer.
      </p>

      <Card title="Open docs" subtitle="Where the master variable list is maintained (T1)">
        <p className="sub" style={{ marginBottom: 12 }}>
          View <span className="mono">docs/VARIABLES.md</span> in the repository for:
          variable definitions, where they are found, and where they are used in code.
        </p>

        <Link className="btn" href="/experiments">Go to Experiments →</Link>
      </Card>
    </div>
  );
}
