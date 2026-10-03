/**
 * LibraScan - Application Configuration & Branding
 */

export const CONFIG = {
  APP_NAME: "LibraScan",
  TAGLINE: "Scan a cover. Catalog a book.",
  VERSION: "2.1.0",
  API_BASE: "",
  MAX_UPLOAD_MB: 10,
  ALLOWED_MIME: ["image/jpeg", "image/png", "image/webp"],
  UNDO_TIMEOUT_MS: 5000,
};

export const FIELD_COLORS = {
  title: "#2563eb",
  subtitle: "#7c3aed",
  authors: "#059669",
  publisher: "#d97706",
  isbn10: "#db2777",
  isbn13: "#0891b2",
  year: "#65a30d",
  edition: "#4f46e5",
  language: "#9333ea",
  series: "#ea580c"
};

export const FIELD_LABELS = {
  title: "Title",
  subtitle: "Subtitle",
  authors: "Authors",
  publisher: "Publisher",
  isbn10: "ISBN-10",
  isbn13: "ISBN-13",
  year: "Publication Year",
  edition: "Edition",
  language: "Language",
  series: "Series"
};
