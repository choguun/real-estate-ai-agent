import { describe, it, expect } from "vitest";
import { ApiError, setAuthToken } from "@/lib/api";

describe("api client", () => {
  it("ApiError carries status", () => {
    const err = new ApiError(401, "nope");
    expect(err.status).toBe(401);
    expect(err.message).toBe("nope");
  });

  it("setAuthToken accepts null without throwing", () => {
    expect(() => setAuthToken(null)).not.toThrow();
  });
});
