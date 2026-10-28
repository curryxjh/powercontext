/// <reference lib="webworker" />

import { pipeline } from "@huggingface/transformers";
import {
  MODEL_DTYPE,
  MODEL_ID,
  type EmbeddingBackend,
} from "../../shared/contracts";

interface TensorLike {
  tolist(): unknown;
}

type Extractor = (
  input: string | string[],
  options: { pooling: "mean"; normalize: boolean },
) => Promise<TensorLike>;

type WorkerRequest =
  | { type: "init" }
  | { type: "embed"; requestId: string; texts: string[] };

type ProgressPayload = Record<string, unknown> & {
  status?: string;
  file?: string;
  progress?: number;
};

let extractor: Extractor | null = null;
let backend: EmbeddingBackend | null = null;
let initialization: Promise<void> | null = null;

function post(type: string, payload: Record<string, unknown> = {}) {
  self.postMessage({ type, ...payload });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function loadPipeline(device: EmbeddingBackend): Promise<Extractor> {
  const loaded = await pipeline("feature-extraction", MODEL_ID, {
    device,
    dtype: MODEL_DTYPE,
    progress_callback: (progress: ProgressPayload) => {
      post("progress", {
        backend: device,
        status: progress.status ?? "loading",
        file: progress.file,
        progress: progress.progress,
      });
    },
  });
  return loaded as unknown as Extractor;
}

async function initialize(): Promise<void> {
  if (extractor) {
    return;
  }
  if (initialization) {
    return initialization;
  }

  initialization = (async () => {
    const startedAt = performance.now();
    let fallbackReason: string | undefined;

    try {
      extractor = await loadPipeline("webgpu");
      backend = "webgpu";
    } catch (error) {
      fallbackReason = errorMessage(error);
      post("fallback", { from: "webgpu", to: "wasm", reason: fallbackReason });
      extractor = await loadPipeline("wasm");
      backend = "wasm";
    }

    post("ready", {
      backend,
      dtype: MODEL_DTYPE,
      modelId: MODEL_ID,
      loadMs: performance.now() - startedAt,
      fallbackReason,
    });
  })().catch((error) => {
    initialization = null;
    post("fatal", { message: errorMessage(error) });
    throw error;
  });

  return initialization;
}

self.addEventListener("message", async (event: MessageEvent<WorkerRequest>) => {
  const message = event.data;
  if (message.type === "init") {
    await initialize().catch(() => undefined);
    return;
  }

  try {
    await initialize();
    if (!extractor || !backend) {
      throw new Error("Embedding model is not ready");
    }

    const startedAt = performance.now();
    const output = await extractor(message.texts, {
      pooling: "mean",
      normalize: true,
    });
    const vectors = output.tolist() as number[][];

    post("result", {
      requestId: message.requestId,
      vectors,
      inferenceMs: performance.now() - startedAt,
      backend,
    });
  } catch (error) {
    post("error", {
      requestId: message.requestId,
      message: errorMessage(error),
    });
  }
});

export {};
