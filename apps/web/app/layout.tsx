import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";
import AuthControl from "@/components/AuthControl";

export const metadata = { title: "VerityForge", description: "Token-efficient coding agent and stale-answer detector" };

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/workspace", label: "Coding Workspace" },
  { href: "/verify", label: "Answer Verification" },
  { href: "/providers", label: "Providers" },
  { href: "/analytics", label: "Token & Cost" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/security", label: "Security" },
  { href: "/repository", label: "Repository" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">
        <header className="border-b border-cyan-500/20 bg-navy-900/80 backdrop-blur">
          <nav aria-label="Main" className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
            <span className="bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-lg font-semibold text-transparent">
              VerityForge
            </span>
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="text-sm text-slate-300 hover:text-cyan-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400">
                {n.label}
              </Link>
            ))}
            <span className="ml-auto">
              <AuthControl />
            </span>
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
