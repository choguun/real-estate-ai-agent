"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { createProperty } from "@/lib/properties";
import type {
  Property,
  PropertyType,
  PropertyCreateInput,
} from "@/lib/types";
import { PROPERTY_TYPE_LABELS_TH } from "@/lib/types";
import { uploadImages } from "@/lib/uploads";
import { ImageUploader } from "./ImageUploader";

const PROPERTY_TYPE_OPTIONS: PropertyType[] = [
  "condo",
  "house",
  "townhouse",
  "land",
  "commercial",
];

export function PropertyForm() {
  const router = useRouter();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [propertyType, setPropertyType] = useState<PropertyType | "">("");
  const [price, setPrice] = useState<string>("");
  const [sizeSqm, setSizeSqm] = useState<string>("");
  const [bedrooms, setBedrooms] = useState<string>("");
  const [bathrooms, setBathrooms] = useState<string>("");
  const [floor, setFloor] = useState<string>("");
  const [address, setAddress] = useState("");
  const [district, setDistrict] = useState("");
  const [province, setProvince] = useState("Bangkok");
  const [nearBtsMrt, setNearBtsMrt] = useState("");
  const [foreignQuota, setForeignQuota] = useState(false);
  const [imageFiles, setImageFiles] = useState<File[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    let imageUrls: string[] = [];
    if (imageFiles.length > 0) {
      setUploadStatus(`Uploading ${imageFiles.length} image(s)…`);
      try {
        const results = await uploadImages(imageFiles);
        imageUrls = results.map((r) => r.url);
      } catch (err) {
        setUploadStatus(null);
        setError(err instanceof ApiError ? err.detail || err.message : "Upload failed");
        return;
      }
      setUploadStatus(null);
    }

    setSubmitting(true);
    const payload: PropertyCreateInput = {
      title: title.trim() || null,
      description: description.trim() || null,
      property_type: propertyType || null,
      price: numOrNull(price),
      size_sqm: numOrNull(sizeSqm),
      bedrooms: numOrNull(bedrooms),
      bathrooms: numOrNull(bathrooms),
      floor: numOrNull(floor),
      address: address.trim() || null,
      district: district.trim() || null,
      province: province.trim() || null,
      near_bts_mrt: nearBtsMrt.trim() || null,
      foreign_quota: foreignQuota,
      images: imageUrls.length > 0 ? imageUrls : null,
    };

    try {
      const created: Property = await createProperty(payload);
      router.push(`/properties/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail || err.message : "Save failed");
      setSubmitting(false);
    }
  }

  const fieldClass =
    "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <form onSubmit={handleSubmit} className="space-y-6" data-testid="property-form">
      {/* ─── Photos ────────────────────────────────────────────── */}
      <section className="rounded-lg border bg-card p-5">
        <h2 className="font-medium">Photos</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          JPG, PNG, WebP, or GIF. Files upload on submit.
        </p>
        <div className="mt-4">
          <ImageUploader onFilesChange={setImageFiles} disabled={submitting} />
        </div>
        {uploadStatus && (
          <p className="mt-3 text-xs text-muted-foreground" data-testid="upload-status">
            {uploadStatus}
          </p>
        )}
      </section>

      {/* ─── Basics ────────────────────────────────────────────── */}
      <section className="rounded-lg border bg-card p-5 space-y-4">
        <h2 className="font-medium">Basics</h2>

        <div className="space-y-1">
          <label htmlFor="title" className="text-sm font-medium">Title</label>
          <input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="คอนโดใจกลางกรุงเทพ"
            className={fieldClass}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="property_type" className="text-sm font-medium">Type</label>
            <select
              id="property_type"
              value={propertyType}
              onChange={(e) => setPropertyType(e.target.value as PropertyType | "")}
              className={fieldClass}
            >
              <option value="">—</option>
              {PROPERTY_TYPE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {PROPERTY_TYPE_LABELS_TH[opt]}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label htmlFor="price" className="text-sm font-medium">Price (THB)</label>
            <input
              id="price"
              type="number"
              min="0"
              step="1000"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className={fieldClass}
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="size_sqm" className="text-sm font-medium">Size (ตร.ม.)</label>
            <input
              id="size_sqm"
              type="number"
              min="0"
              step="0.5"
              value={sizeSqm}
              onChange={(e) => setSizeSqm(e.target.value)}
              className={fieldClass}
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="bedrooms" className="text-sm font-medium">Bedrooms</label>
            <input
              id="bedrooms"
              type="number"
              min="0"
              value={bedrooms}
              onChange={(e) => setBedrooms(e.target.value)}
              className={fieldClass}
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="bathrooms" className="text-sm font-medium">Bathrooms</label>
            <input
              id="bathrooms"
              type="number"
              min="0"
              value={bathrooms}
              onChange={(e) => setBathrooms(e.target.value)}
              className={fieldClass}
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="floor" className="text-sm font-medium">Floor</label>
            <input
              id="floor"
              type="number"
              min="0"
              value={floor}
              onChange={(e) => setFloor(e.target.value)}
              className={fieldClass}
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={foreignQuota}
            onChange={(e) => setForeignQuota(e.target.checked)}
          />
          Available under foreign quota (โควต้าต่างชาติ)
        </label>
      </section>

      {/* ─── Location ──────────────────────────────────────────── */}
      <section className="rounded-lg border bg-card p-5 space-y-4">
        <h2 className="font-medium">Location</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1 sm:col-span-2">
            <label htmlFor="address" className="text-sm font-medium">Address</label>
            <input
              id="address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className={fieldClass}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="district" className="text-sm font-medium">District (เขต)</label>
            <input
              id="district"
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              className={fieldClass}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="province" className="text-sm font-medium">Province (จังหวัด)</label>
            <input
              id="province"
              value={province}
              onChange={(e) => setProvince(e.target.value)}
              className={fieldClass}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <label htmlFor="near_bts_mrt" className="text-sm font-medium">Near BTS/MRT</label>
            <input
              id="near_bts_mrt"
              value={nearBtsMrt}
              onChange={(e) => setNearBtsMrt(e.target.value)}
              placeholder="BTS Asok, MRT Sukhumvit"
              className={fieldClass}
            />
          </div>
        </div>
      </section>

      {/* ─── Description ───────────────────────────────────────── */}
      <section className="rounded-lg border bg-card p-5 space-y-1">
        <label htmlFor="description" className="text-sm font-medium">Description</label>
        <textarea
          id="description"
          rows={4}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="ห้องนอนใหญ่ เฟอร์นิเจอร์ครบ วิวเมือง..."
          className={fieldClass}
        />
      </section>

      {/* ─── Submit ────────────────────────────────────────────── */}
      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      )}

      <div className="flex justify-end gap-3">
        <button
          type="button"
          onClick={() => router.back()}
          className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          data-testid="submit-property"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save property"}
        </button>
      </div>
    </form>
  );
}

function numOrNull(s: string): number | null {
  if (s === "" || s === null || s === undefined) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
