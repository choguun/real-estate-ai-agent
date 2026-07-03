import Link from "next/link";

/**
 * Auth-gated shell for the (app) route group. Pages under this group are
 * client components that handle token checks themselves before fetching;
 * this layout provides the chrome (nav, container) only.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link href="/dashboard" className="text-sm font-semibold tracking-tight">
            🏠 Real Estate AI Agent
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/dashboard" className="text-muted-foreground hover:text-foreground">
              Dashboard
            </Link>
            <Link href="/properties" className="text-muted-foreground hover:text-foreground">
              Properties
            </Link>
            <Link href="/leads" className="text-muted-foreground hover:text-foreground">
              Leads
            </Link>
            <Link href="/settings" className="text-muted-foreground hover:text-foreground">
              Settings
            </Link>
          </nav>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-6 py-8">{children}</div>
    </div>
  );
}
