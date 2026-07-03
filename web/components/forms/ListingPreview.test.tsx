import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";


import { ListingPreview } from "@/components/forms/ListingPreview";
import type { GeneratedContent } from "@/lib/types";

const sample: GeneratedContent[] = [
  {
    platform: "ddproperty",
    title: "คอนโด 1 ห้องนอน 35 ตร.ม.",
    description: "ขายคอนโด ทำเลดี ใกล้ BTS อโศก",
    hashtags: [],
    seo_keywords: ["คอนโด", "Bangkok"],
    ai_model: "claude-3-5-sonnet-mock",
  },
  {
    platform: "facebook",
    title: "🔥 ขายคอนโด",
    description: "🚨 ขายด่วน! คอนโด\n💰 ฿5,500,000\nสนใจ DM",
    hashtags: ["#คอนโด", "#Bangkok", "#ขาย", "#ลงทุน", "#อสังหา", "#ขายคอนโด"],
    seo_keywords: [],
    ai_model: "claude-3-5-sonnet-mock",
  },
];

describe("ListingPreview", () => {
  it("renders one tab per platform", () => {
    render(<ListingPreview contents={sample} />);
    expect(screen.getByTestId("tab-ddproperty")).toBeInTheDocument();
    expect(screen.getByTestId("tab-facebook")).toBeInTheDocument();
    expect(screen.queryByTestId("tab-livinginsider")).toBeNull();
    expect(screen.queryByTestId("tab-general")).toBeNull();
  });

  it("shows the first platform by default", () => {
    render(<ListingPreview contents={sample} />);
    expect(screen.getByText(/คอนโด 1 ห้องนอน/)).toBeInTheDocument();
  });

  it("respects initialPlatform", () => {
    render(<ListingPreview contents={sample} initialPlatform="facebook" />);
    expect(screen.getByText(/🚨 ขายด่วน/)).toBeInTheDocument();
  });

  it("renders hashtags when present", () => {
    render(<ListingPreview contents={sample} initialPlatform="facebook" />);
    expect(screen.getByText(/#คอนโด/)).toBeInTheDocument();
  });

  it("shows AI model in header", () => {
    render(<ListingPreview contents={sample} />);
    expect(screen.getByText(/claude-3-5-sonnet-mock/)).toBeInTheDocument();
  });

  it("returns null when contents is empty", () => {
    const { container } = render(<ListingPreview contents={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
