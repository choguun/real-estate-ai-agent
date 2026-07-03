import { NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { cache: "no-store" });
    if (!res.ok) {
      return NextResponse.json(
        { status: "down", backend: res.status },
        { status: 503 },
      );
    }
    const data = (await res.json()) as { status: string };
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { status: "down", backend: "unreachable" },
      { status: 503 },
    );
  }
}
