export const EMBEDDING_DIMENSION = 384;
export const MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
export const MODEL_DTYPE = "q8";
export const MAX_BATCH_SIZE = 64;
export const COLLECTION_NAME_PATTERN = /^[a-z][a-z0-9_]{2,47}$/;

export type EmbeddingBackend = "webgpu" | "wasm";

export interface CollectionSummary {
  name: string;
  count: number;
  dimension: number;
  distance: string;
}

export interface DocumentRecord {
  id: string;
  document: string;
  embedding: number[];
  metadata: Record<string, string | number | boolean>;
}

export interface ImportResponse {
  collection: string;
  upserted: number;
  total: number;
  writeMs: number;
  refreshMs: number;
}

export interface SearchResultItem {
  id: string;
  document: string;
  metadata: Record<string, unknown> | null;
  distance: number | null;
}

export interface SearchResponse {
  collection: string;
  databaseMs: number;
  results: SearchResultItem[];
}

export interface HealthResponse {
  ok: boolean;
  mode: "server";
  target: string;
  database: string;
  message?: string;
}
