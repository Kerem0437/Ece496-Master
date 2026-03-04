import { redirect } from "next/navigation";

export default function HomePage() {
  // Simple landing behavior: go directly to Experiments.
  // Keeps the demo flow immediate for supervisors.
  redirect("/experiments");
}
//