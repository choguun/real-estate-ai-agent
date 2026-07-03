import Link from "next/link";
import { PropertyForm } from "@/components/forms/PropertyForm";

export default function NewPropertyPage() {
  return (
    <main>
      <div className="mb-6">
        <Link href="/properties" className="text-sm text-muted-foreground hover:text-foreground">
          ← All properties
        </Link>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">New property</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Fill in the basics now — you can refine and generate listings after saving.
        </p>
      </div>
      <PropertyForm />
    </main>
  );
}
