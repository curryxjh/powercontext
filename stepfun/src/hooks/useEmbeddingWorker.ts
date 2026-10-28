import { useCallback, useEffect, useRef, useState } from "react";
import type { EmbeddingBackend } from "../../shared/contracts";

interface ModelState {
  status: "loading" | "ready" | "error";
  backend: EmbeddingBackend | null;
  progress: number | null;
  currentFile: string | null;
  loadMs: number | null;
  fallbackReason: string | null;
  error: string | null;
}

interface EmbedResult {
  vectors: number[][];
  inferenceMs: number;
  backend: EmbeddingBackend;
}

interface PendingRequest {
  resolve: (result: EmbedResult) => void;
  reject: (error: Error) => void;
}

const initialState: ModelState = {
  status: "loading",
  backend: null,
  progress: null,
  currentFile: null,
  loadMs: null,
  fallbackReason: null,
  error: null,
};

export function useEmbeddingWorker() {
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef(new Map<string, PendingRequest>());
  const [model, setModel] = useState<ModelState>(initialState);

  useEffect(() => {
    const worker = new Worker(new URL("../workers/embedding.worker.ts", import.meta.url), {
      type: "module",
    });
    workerRef.current = worker;

    worker.addEventListener("message", (event: MessageEvent<Record<string, unknown>>) => {
      const message = event.data;
      switch (message.type) {
        case "progress":
          setModel((current) => ({
            ...current,
            progress: typeof message.progress === "number" ? message.progress : null,
            currentFile: typeof message.file === "string" ? message.file : null,
          }));
          break;
        case "fallback":
          setModel((current) => ({
            ...current,
            fallbackReason: String(message.reason),
          }));
          break;
        case "ready":
          setModel((current) => ({
            ...current,
            status: "ready",
            backend: message.backend as EmbeddingBackend,
            loadMs: Number(message.loadMs),
            fallbackReason:
              typeof message.fallbackReason === "string"
                ? message.fallbackReason
                : current.fallbackReason,
            progress: 100,
            error: null,
          }));
          break;
        case "fatal":
          setModel((current) => ({
            ...current,
            status: "error",
            error: String(message.message),
          }));
          break;
        case "result": {
          const requestId = String(message.requestId);
          const pending = pendingRef.current.get(requestId);
          if (pending) {
            pendingRef.current.delete(requestId);
            pending.resolve({
              vectors: message.vectors as number[][],
              inferenceMs: Number(message.inferenceMs),
              backend: message.backend as EmbeddingBackend,
            });
          }
          break;
        }
        case "error": {
          const requestId = String(message.requestId);
          const pending = pendingRef.current.get(requestId);
          if (pending) {
            pendingRef.current.delete(requestId);
            pending.reject(new Error(String(message.message)));
          }
          break;
        }
      }
    });

    worker.postMessage({ type: "init" });

    return () => {
      worker.terminate();
      for (const pending of pendingRef.current.values()) {
        pending.reject(new Error("Embedding worker was stopped"));
      }
      pendingRef.current.clear();
      workerRef.current = null;
    };
  }, []);

  const embed = useCallback((texts: string[]): Promise<EmbedResult> => {
    if (!workerRef.current) {
      return Promise.reject(new Error("Embedding worker is unavailable"));
    }
    const requestId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      pendingRef.current.set(requestId, { resolve, reject });
      workerRef.current?.postMessage({ type: "embed", requestId, texts });
    });
  }, []);

  return { model, embed };
}
