import Link from "next/link";

interface NewLeadsCounterProps {
  count: number;
}

export function NewLeadsCounter({ count }: NewLeadsCounterProps) {
  const dimmed = count === 0;
  return (
    <Link
      href="/leads"
      data-testid="new-leads-counter"
      data-count={count}
      className={`block rounded-lg border bg-card p-5 shadow-sm transition ${
        dimmed ? "opacity-60" : "hover:shadow-md"
      }`}
    >
      <p className="text-sm font-medium text-muted-foreground">New leads</p>
      <p
        className={`mt-2 text-4xl font-bold tracking-tight ${
          dimmed ? "text-muted-foreground" : "text-emerald-600"
        }`}
      >
        {count}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {count === 0 ? "ดูเหมือนว่าง — nothing pending" : "จะเปลี่ยนเป็นติดต่อแล้วเมื่อคุย"}
      </p>
    </Link>
  );
}
