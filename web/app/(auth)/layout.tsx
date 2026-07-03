import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-muted/30">
      <div className="mx-auto flex min-h-screen max-w-md flex-col px-4 py-12">
        <Link href="/" className="mb-8 text-sm text-muted-foreground hover:text-foreground">
          ← Back home
        </Link>
        <div className="rounded-lg border bg-card p-8 shadow-sm">
          {children}
        </div>
      </div>
    </main>
  );
}
