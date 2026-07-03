// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const getDashboardMock = vi.fn();
const fetchMeMock = vi.fn();
const getAuthTokenMock = vi.fn();

vi.mock("@/lib/dashboard", () => ({
  getDashboard: (...args: unknown[]) => getDashboardMock(...args),
}));

vi.mock("@/lib/auth", () => ({
  fetchMe: (...args: unknown[]) => fetchMeMock(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useParams: () => ({}),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getAuthToken: () => getAuthTokenMock(),
    clearAuthToken: () => undefined,
    ApiError: class ApiError extends Error {
      public readonly status: number;
      constructor(status: number, msg: string) {
        super(msg);
        this.status = status;
      }
    },
  };
});

// Late-import after mocks so the page picks them up.
beforeEach(async () => {
  vi.resetModules();
  getDashboardMock.mockReset();
  fetchMeMock.mockReset();
  getAuthTokenMock.mockReset();
  getAuthTokenMock.mockReturnValue("jwt");
  fetchMeMock.mockResolvedValue({
    id: "u-1",
    email: "a@example.com",
    full_name: "Agent",
  });
});

describe("DashboardPage (ST-014 frontend)", () => {
  it("renders all three sections when /api/dashboard returns the standard payload", async () => {
    getDashboardMock.mockResolvedValue({
      new_leads_count: 2,
      recent_inbound: [
        {
          id: "m-1",
          lead_id: "l-1",
          user_id: "u-1",
          direction: "inbound",
          message_type: "text",
          content: "I’m interested in this condo",
          is_ai_generated: false,
          created_at: "2026-07-03T07:00:00Z",
          lead: { id: "l-1", line_user_id: "U-alice", name: null },
        },
      ],
      recent_properties: [
        {
          id: "p-1",
          user_id: "u-1",
          team_id: null,
          title: "คอนโดทดสอบ",
          description: null,
          property_type: "condo",
          price: 5_500_000,
          size_sqm: 35,
          bedrooms: 1,
          bathrooms: 1,
          floor: 12,
          address: null,
          district: "Khlong Toei",
          province: "Bangkok",
          near_bts_mrt: null,
          foreign_quota: false,
          status: "draft",
          images: null,
          created_at: "2026-07-03T00:00:00Z",
          updated_at: "2026-07-03T00:00:00Z",
        },
      ],
    });
    const { default: DashboardPage } = await import("@/app/(app)/dashboard/page");
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByTestId("greeting")).toHaveTextContent("Agent");
    });

    // ST-014 — all three sections are visible.
    expect(screen.getByTestId("greeting")).toBeInTheDocument();
    expect(screen.getByTestId("new-leads-counter")).toBeInTheDocument();
    expect(screen.getByTestId("new-leads-counter")).toHaveAttribute("data-count", "2");
    expect(screen.getByTestId("recent-messages")).toBeInTheDocument();
    expect(screen.getByText(/interested in this condo/i)).toBeInTheDocument();
    expect(screen.getByTestId("recent-properties")).toBeInTheDocument();
    expect(screen.getByText("คอนโดทดสอบ")).toBeInTheDocument();
  });

  it("dims the counter when there are zero new leads", async () => {
    getDashboardMock.mockResolvedValue({
      new_leads_count: 0,
      recent_inbound: [],
      recent_properties: [],
    });
    const { default: DashboardPage } = await import("@/app/(app)/dashboard/page");
    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByTestId("new-leads-counter")).toHaveAttribute("data-count", "0");
    });
    // 0 case has dimmed styling — class contains opacity-60.
    const counter = screen.getByTestId("new-leads-counter");
    expect(counter.className).toMatch(/opacity-60/);
  });
});
