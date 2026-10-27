---
title: Configure vector search
description: Enable embedding-backed vector and hybrid Memory search, then verify the Runtime capability.
---

# Configure vector search

Vector search needs an embedding model, a stable profile ID, and the model's output dimension.

## 1. Set one embedding profile

```bash
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_MODEL=provider:embedding-model
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_PROFILE_ID=embedding-model-v1
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_DIMENSION=1024
```

Replace the example values with one supported provider model, a profile ID you keep stable for that model, and its
documented output dimension. `POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_NORMALIZATION` defaults to `unit`.

The output dimension is always required. It fixes the local vector index width and validates returned vectors. By
default that value is also sent as the `dimensions` request field. Some OpenAI-compatible services reject the field,
including SiliconFlow `BAAI/bge-m3`. Keep the documented output dimension (1024 for bge-m3) and disable sending:

```bash
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_SEND_DIMENSIONS=false
```

## 2. Start the Server

```bash
powercontext server run
```

With SQLite, PowerContext loads the bundled sqlite-vec extension when it opens the database. Startup fails if the
installed extension is incompatible with the platform or SQLite build.

## 3. Verify the capability

```bash
powercontext capabilities
```

The result reports the enabled search modes. Without an embedding profile, SQLite full-text search remains available.

For timeouts, batch size, storage settings, and exact defaults, see [Configuration](../operate/configuration.md).

## Share SDK embedding requests

SDK applications can opt into request coalescing and a bounded vector cache by wrapping an existing `EmbeddingModel`.
Share one wrapper across calls on the same event loop, and inject it into the Runtime:

```python
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel
from powercontext.builtin.runtime import open_builtin_contexts

model = CoalescingEmbeddingModel(
    base_model, max_batch_size=64, coalesce_ms=5.0, cache_size=1024
)
async with open_builtin_contexts(config, embedding_model=model) as contexts:
    scope = await contexts.get("project")
    # Use scope.artifacts.memory to write and search Memory as usual.
```

`max_batch_size` limits the number of distinct texts in each provider call. `coalesce_ms` is a nonnegative batching
window in milliseconds; zero still allows calls already runnable together to share work. `cache_size` is the maximum
number of successful text vectors retained in an LRU cache. Zero disables completed-result caching while keeping
in-flight sharing. Batch size and cache capacity require integers; batch size must be positive and capacity nonnegative.

Each call receives vectors in its original order, including duplicates. Its `usage` sums each distinct provider batch
it awaited once, preserving reported request and token counts. Shared batches can appear in several callers' usage;
these per-call values do not represent an exclusive allocation of provider billing. Pure cache hits report zero
requests. Unknown token counts remain `None` when no contributing batch reports them; otherwise known counts are summed.

Cancelling one caller leaves shared work running. Provider failures and incorrect vector counts fail dependent callers
without poisoning the cache or stopping independent batches. Failed texts can be retried. Query-aware providers keep
query and document work separate; symmetric providers share vectors across both operations.

The wrapper retains the model's profile. Cache contents stay within the wrapper instance, are not persisted, and are
not shared between worker processes. Model/profile configuration must stay fixed for the wrapper's lifetime.
Existing applications keep their original behavior unless they explicitly wrap the model.
