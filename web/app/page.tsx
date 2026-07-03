import Link from "next/link";
import { checkBackendHealth } from "@/lib/api";

export default async function HomePage() {
  let backendStatus: "ok" | "down" = "down";
  try {
    const data = await checkBackendHealth();
    backendStatus = data.status === "ok" ? "ok" : "down";
  } catch {
    backendStatus = "down";
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-4xl font-bold tracking-tight">
        Real Estate AI Agent 🇹🇭
      </h1>
      <p className="mt-4 text-lg text-muted-foreground">
        LINE-integrated AI listing generator + lead inbox for Thai agents.
      </p>

      <div
        data-testid="backend-status"
        className="mt-10 rounded-lg border p-4"
      >
        <div className="flex items-center gap-3">
          <span
            data-status={backendStatus}
            className={`inline-block h-3 w-3 rounded-full ${
              backendStatus === "ok" ? "bg-green-500" : "bg-red-500"
            }`}
            aria-hidden
          />
          <span className="text-sm">
            Backend: <strong>{backendStatus}</strong>
          </span>
        </div>
      </div>

      <div className="mt-8 flex gap-4">
        <Link
          href="/login"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Log in
        </Link>
        <Link
          href="/signup"
          className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
        >
          Sign up
        </Link>
      </div>
    </main>
  );
}
