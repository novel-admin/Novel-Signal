import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Novel Signal",
  description: "Evidence-first competitive intelligence",
};

const links = [
  ["Universe", "/universe"], ["Keywords", "/keywords"], ["Collection", "/collection"], ["Rank & Visibility", "/rank-visibility"], ["Listing Intelligence", "/listing-intelligence"], ["Price Monitoring", "/price-monitoring"], ["Products", "/products"],
  ["Sources", "/sources"], ["Ads", "/ads"], ["Reviews", "/reviews"], ["Market Share", "/market-share"], ["Scorecards", "/scorecards"], ["Alerts", "/alerts"], ["Changes", "/changes"], ["Actions", "/actions"], ["Operations", "/operations"],
] as const;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">Novel Signal</div>
            <nav className="nav">
              <Link href="/">Overview</Link>
              {links.map(([label, href]) => (
                <Link key={label} href={href}>{label}</Link>
              ))}
            </nav>
          </aside>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
