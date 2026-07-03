"use client";

import { useEffect, useRef, useState } from "react";

export interface ImageUploaderProps {
  /** Called whenever the user picks new files. Files are stored as-is;
   *  uploading happens in the parent on submit. */
  onFilesChange: (files: File[]) => void;
  /** Pre-existing URLs (e.g. when editing an existing property). */
  existingUrls?: string[];
  disabled?: boolean;
}

interface Preview {
  file: File;
  url: string;
}

export function ImageUploader({ onFilesChange, existingUrls = [], disabled }: ImageUploaderProps) {
  const [previews, setPreviews] = useState<Preview[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Revoke every object URL whenever the preview list changes OR on
  // unmount. Before this fix, only the unmount path revoked URLs, which
  // leaked every prior batch's blob refs when the user picked again.
  useEffect(() => {
    return () => {
      previews.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, [previews]);

  function handleSelected(files: FileList | null) {
    if (!files || files.length === 0) return;
    const picked = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (picked.length === 0) return;
    const next: Preview[] = picked.map((file) => ({ file, url: URL.createObjectURL(file) }));
    setPreviews(next);
    onFilesChange(picked);
    if (inputRef.current) inputRef.current.value = "";
  }

  function removeAt(index: number) {
    setPreviews((prev) => {
      const next = prev.slice();
      const [removed] = next.splice(index, 1);
      if (removed) URL.revokeObjectURL(removed.url);
      onFilesChange(next.map((p) => p.file));
      return next;
    });
  }

  return (
    <div className="space-y-3" data-testid="image-uploader">
      <div className="flex flex-wrap gap-3">
        {existingUrls.map((url, i) => (
          <div
            key={`existing-${i}`}
            className="relative h-24 w-24 overflow-hidden rounded-md border bg-muted"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url}
              alt={`Existing image ${i + 1}`}
              className="h-full w-full object-cover"
            />
          </div>
        ))}
        {previews.map((p, i) => (
          <div
            key={`preview-${i}`}
            className="relative h-24 w-24 overflow-hidden rounded-md border bg-muted"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={p.url}
              alt={p.file.name}
              className="h-full w-full object-cover"
              data-testid="preview-image"
            />
            {!disabled && (
              <button
                type="button"
                aria-label={`Remove ${p.file.name}`}
                onClick={() => removeAt(i)}
                className="absolute right-1 top-1 rounded-full bg-background/90 px-1.5 text-xs shadow"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>

      <label
        htmlFor="image-input"
        className={`inline-flex cursor-pointer items-center rounded-md border border-dashed px-4 py-2 text-sm transition ${
          disabled ? "pointer-events-none opacity-50" : "hover:bg-accent"
        }`}
      >
        📷 Add photos
        <input
          id="image-input"
          ref={inputRef}
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={(e) => handleSelected(e.target.files)}
          disabled={disabled}
        />
      </label>
    </div>
  );
}
