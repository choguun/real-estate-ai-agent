/** Upload helpers — wraps `/api/upload-image`. */

import { apiUpload } from "./api";

export interface UploadResult {
  url: string;
  key: string;
  content_type: string;
  size: number;
}

export async function uploadImage(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return apiUpload<UploadResult>("/api/upload-image", fd);
}

export async function uploadImages(files: File[]): Promise<UploadResult[]> {
  // Sequential is fine for MVP; could parallelise in T-012.
  const out: UploadResult[] = [];
  for (const file of files) {
    out.push(await uploadImage(file));
  }
  return out;
}
