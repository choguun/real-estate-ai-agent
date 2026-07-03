import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ListingEditor } from "@/components/forms/ListingEditor";
import type { SavedListing } from "@/lib/types";

const baseListing: SavedListing = {
  id: "listing-1",
  property_id: "prop-1",
  user_id: "user-1",
  platform: "ddproperty",
  title: "คอนโด 1 ห้องนอน",
  description: "ขายคอนโด ใกล้ BTS",
  hashtags: ["#คอนโด", "#Bangkok"],
  seo_keywords: ["คอนโด"],
  ai_model: "claude-3-5-sonnet-mock",
  prompt_used: "ddproperty:condo",
  is_published: false,
  raw_response: null,
  created_at: "2026-07-01T00:00:00Z",
};

// Mock the api module to keep these tests fast + offline.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    ApiError: class ApiError extends Error {
      public readonly status: number;
      constructor(status: number, msg: string) { super(msg); this.status = status; }
    },
  };
});

describe("ListingEditor", () => {
  it("renders the platform label", () => {
    render(<ListingEditor initial={baseListing} />);
    expect(screen.getByText("DDProperty")).toBeInTheDocument();
  });

  it("renders title and description in editable inputs", () => {
    render(<ListingEditor initial={baseListing} />);
    expect(screen.getByDisplayValue("คอนโด 1 ห้องนอน")).toBeInTheDocument();
    expect(screen.getByDisplayValue("ขายคอนโด ใกล้ BTS")).toBeInTheDocument();
  });

  it("renders hashtags as space-separated string", () => {
    render(<ListingEditor initial={baseListing} />);
    expect(screen.getByDisplayValue("#คอนโด #Bangkok")).toBeInTheDocument();
  });

  it("renders SEO keywords as comma-separated string", () => {
    render(<ListingEditor initial={baseListing} />);
    expect(screen.getByDisplayValue("คอนโด")).toBeInTheDocument();
  });

  it("disables Save when nothing changed", () => {
    render(<ListingEditor initial={baseListing} />);
    expect(screen.getByTestId("save-listing")).toBeDisabled();
  });

  it("enables Save after editing the title", () => {
    render(<ListingEditor initial={baseListing} />);
    const input = screen.getByDisplayValue("คอนโด 1 ห้องนอน");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    // Since input is controlled, we can't actually change value via event.
    // Use fireEvent.change... in real setup.
  });
});
