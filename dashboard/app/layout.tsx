import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Water Dashboard (T1–T5)",
  description: "Mock-data scaffold for Experiments List + Detail (Vercel-ready)."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="appShell">
          <header className="topBar">
            <div className="brand">
              <div className="brandDot" />
              <div>
                <div className="brandTitle">Water Dashboard</div>
                <div className="brandSub">T1–T5 scaffold (mock data)</div>
              </div>
            </div>

            <nav className="nav">
              <a className="navLink" href="/experiments">Experiments</a>
              <a className="navLink" href="/docs/variables">Variables</a>
            </nav>
          </header>

          <main className="main">{children}</main>

          <footer className="footer">
            <span>Mock-only • Stop at T5 • Ready for Vercel</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
