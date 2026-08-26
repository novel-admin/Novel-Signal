"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BellRing,
  ChartNoAxesCombined,
  ClipboardCheck,
  Database,
  FileSearch,
  KeyRound,
  LayoutDashboard,
  PackageSearch,
  Search,
  Settings2,
  Target,
} from "lucide-react";
import { cn } from "../lib/cn";

const groups = [
  { label: "Monitor", links: [["Overview", "/", LayoutDashboard], ["Keywords", "/keywords", Search], ["Rank & Visibility", "/rank-visibility", Search], ["Products", "/products", PackageSearch], ["Listing Intelligence", "/listing-intelligence", FileSearch], ["Price Monitoring", "/price-monitoring", ChartNoAxesCombined], ["Advertising", "/ads", Target], ["Changes", "/changes", Activity]] },
  { label: "Decide", links: [["Scorecards", "/scorecards", ChartNoAxesCombined], ["Actions", "/actions", ClipboardCheck], ["Alerts", "/alerts", BellRing]] },
  { label: "Manage", links: [["Universe", "/universe", Database], ["Sources", "/sources", KeyRound], ["Operations", "/operations", FileSearch], ["Settings", "/collection", Settings2]] },
] as const;

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link className="brand" href="/"><span className="brand-mark">N</span><span>Novel Signal</span></Link>
      <nav className="nav" aria-label="Primary navigation">
        {groups.map((group) => <div className="nav-group" key={group.label}><span className="nav-group-label">{group.label}</span>{group.links.map(([label, href, Icon]) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return <Link className={cn("nav-link", active && "active")} aria-current={active ? "page" : undefined} href={href} key={href}><Icon size={16} aria-hidden="true" /><span>{label}</span></Link>;
        })}</div>)}
      </nav>
    </aside>
  );
}
