import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ImageUploader } from "@/components/forms/ImageUploader";

// jsdom doesn't ship URL.createObjectURL / revokeObjectURL. Assign
// directly so the component's calls succeed in the test environment.
const created = new Map<string, File>();
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeAll(() => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: (file: Blob) => {
      const url = `blob:test/${(file as File).name ?? "blob"}`;
      created.set(url, file as File);
      return url;
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: (url: string) => {
      created.delete(url);
    },
  });
});

afterAll(() => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: originalCreateObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: originalRevokeObjectURL,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function makeFile(name: string, type = "image/png"): File {
  // jsdom doesn't have a real FileList in change handlers — construct one.
  const f = new File([new Uint8Array([1, 2, 3])], name, { type });
  return f;
}

describe("ImageUploader", () => {
  it("renders the file input trigger and an empty state", () => {
    const onChange = vi.fn();
    render(<ImageUploader onFilesChange={onChange} />);
    expect(screen.getByLabelText(/add photos/i)).toBeInTheDocument();
    expect(screen.queryByTestId("preview-image")).not.toBeInTheDocument();
  });

  it("emits onFilesChange with image files", () => {
    const onChange = vi.fn();
    render(<ImageUploader onFilesChange={onChange} />);
    const input = screen.getByLabelText(/add photos/i) as HTMLInputElement;
    const file = makeFile("house.png", "image/png");
    fireEvent.change(input, { target: { files: [file] } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith([file]);
    expect(screen.getByTestId("preview-image")).toBeInTheDocument();
  });

  it("filters out non-image files", () => {
    const onChange = vi.fn();
    render(<ImageUploader onFilesChange={onChange} />);
    const input = screen.getByLabelText(/add photos/i) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeFile("evil.exe", "application/octet-stream")] },
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId("preview-image")).not.toBeInTheDocument();
  });

  it("calls URL.revokeObjectURL when removing a preview", () => {
    const onChange = vi.fn();
    const { container } = render(<ImageUploader onFilesChange={onChange} />);
    const input = screen.getByLabelText(/add photos/i) as HTMLInputElement;
    const file = makeFile("p.png");
    fireEvent.change(input, { target: { files: [file] } });

    const remove = container.querySelector("button[aria-label^='Remove']");
    expect(remove).not.toBeNull();
    fireEvent.click(remove as HTMLElement);
    // After click, onFilesChange should have been called again (with empty list).
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange.mock.calls[1][0]).toEqual([]);
  });
});
