import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ComposeBox } from "@/components/chat/ComposeBox";

const sendReplyMock = vi.fn();
vi.mock("@/lib/messages", () => ({
  sendReply: (...args: unknown[]) => sendReplyMock(...args),
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    ApiError: class ApiError extends Error {
      public readonly status: number;
      constructor(status: number, msg: string) {
        super(msg);
        this.status = status;
      }
    },
  };
});

beforeEach(() => {
  sendReplyMock.mockReset();
  sendReplyMock.mockResolvedValue({
    message: { id: "m-1", direction: "outbound", content: "hi" },
    line_reply: { id: "r-1", line_user_id: "U-1", sent_at: "2026-07-03T00:00:00Z" },
  });
});

describe("ComposeBox", () => {
  it("disables Send when the textarea is empty", () => {
    render(<ComposeBox leadId="lead-1" onSent={() => undefined} />);
    expect(screen.getByTestId("send-reply")).toBeDisabled();
  });

  it("calls sendReply with the typed text and fires onSent", async () => {
    const onSent = vi.fn();
    render(<ComposeBox leadId="lead-42" onSent={onSent} />);
    const textarea = screen.getByTestId("reply-text") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "สวัสดีครับ" } });

    const btn = screen.getByTestId("send-reply") as HTMLButtonElement;
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);

    await waitFor(() => {
      expect(sendReplyMock).toHaveBeenCalledWith("lead-42", "สวัสดีครับ");
      expect(onSent).toHaveBeenCalledTimes(1);
    });

    // textarea is cleared after successful send
    expect(textarea.value).toBe("");
  });

  it("surfaces the backend's detail string when sendReply throws an ApiError", async () => {
    // The component imports `ApiError` from `@/lib/api`; the mock module
    // exports a structurally identical class, so the same `instanceof`
    // check passes for instances of the mock.
    const { ApiError } = await import("@/lib/api");
    sendReplyMock.mockRejectedValueOnce(new ApiError(503, "Upstream offline"));
    render(<ComposeBox leadId="lead-1" onSent={() => undefined} />);
    const textarea = screen.getByTestId("reply-text") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.click(screen.getByTestId("send-reply"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/Upstream offline/i);
    });
  });

  it("falls back to 'Send failed' for non-ApiError rejections", async () => {
    sendReplyMock.mockRejectedValueOnce(new Error("network down"));
    render(<ComposeBox leadId="lead-1" onSent={() => undefined} />);
    const textarea = screen.getByTestId("reply-text") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.click(screen.getByTestId("send-reply"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/send failed/i);
    });
  });
});
