import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { PropertyCard } from "@/components/properties/PropertyCard";
import type { Property } from "@/lib/types";

const baseProperty: Property = {
  id: "p-1",
  user_id: "u-1",
  title: "คอนโดใจกลางกรุงเทพ",
  description: null,
  property_type: "condo",
  price: 5_500_000,
  size_sqm: 35,
  bedrooms: 1,
  bathrooms: 1,
  floor: 12,
  address: "123 ถ.สุขุมวิท",
  district: "Khlong Toei",
  province: "Bangkok",
  near_bts_mrt: "BTS Asok",
  foreign_quota: true,
  status: "active",
  images: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-02T00:00:00Z",
};

describe("PropertyCard", () => {
  it("renders title, district, province, formatted price", () => {
    render(<PropertyCard property={baseProperty} />);
    expect(screen.getByText("คอนโดใจกลางกรุงเทพ")).toBeInTheDocument();
    expect(screen.getByText("Khlong Toei, Bangkok")).toBeInTheDocument();
    expect(screen.getByText("฿5,500,000")).toBeInTheDocument();
  });

  it("renders the property_type label in Thai", () => {
    render(<PropertyCard property={baseProperty} />);
    expect(screen.getByText("คอนโด")).toBeInTheDocument();
  });

  it("renders bedrooms, bathrooms, BTS line when present", () => {
    render(<PropertyCard property={baseProperty} />);
    expect(screen.getByText(/1 ห้องนอน/)).toBeInTheDocument();
    expect(screen.getByText(/1 ห้องน้ำ/)).toBeInTheDocument();
    expect(screen.getByText(/BTS Asok/)).toBeInTheDocument();
  });

  it("falls back to 'Untitled listing' when title is null", () => {
    render(<PropertyCard property={{ ...baseProperty, title: null }} />);
    expect(screen.getByText("Untitled listing")).toBeInTheDocument();
  });

  it("renders the status pill", () => {
    render(<PropertyCard property={{ ...baseProperty, status: "draft" }} />);
    expect(screen.getByText("draft")).toBeInTheDocument();
  });
});
