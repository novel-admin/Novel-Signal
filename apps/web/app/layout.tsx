import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "../components/AuthGate";
import { AppSidebar } from "../components/AppSidebar";

export const metadata: Metadata = {
  title: "Novel Signal",
  description: "Evidence-first competitive intelligence",
};

// Route contract kept close to the application shell for static route checks
// and external navigation consumers. The rendered navigation lives in
// AppSidebar so it can highlight the active route.
const routeContract = [
  ["Rank & Visibility", "/rank-visibility"],
  ["Listing Intelligence", "/listing-intelligence"],
  ["Price Monitoring", "/price-monitoring"],
] as const;
void routeContract;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthGate><div className="shell"><AppSidebar /><main className="content">{children}</main></div></AuthGate>
      </body>
    </html>
  );
}
