import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Novel Signal",
  description: "Evidence-first competitive intelligence",
};

const links = ["Universe", "Keywords", "Products", "Sources", "Changes", "Actions", "Operations"];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">Novel Signal</div>
            <nav className="nav">
              <Link href="/">Overview</Link>
              {links.map((label) => (
                <Link key={label} href={`/${label.toLowerCase()}`}>{label}</Link>
              ))}
            </nav>
          </aside>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
