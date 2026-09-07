"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AppSidebar } from "./AppSidebar";
import { SourceModeBanner } from "./SourceModeBanner";

const PUBLIC_PREFIXES = ["/login", "/verify-email", "/first-login", "/forgot-password", "/reset-password", "/auth"];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (isPublic) return <main className="content">{children}</main>;
  return (
    <div className="shell">
      <AppSidebar />
      <main className="content">
        <SourceModeBanner />
        {children}
      </main>
    </div>
  );
}
