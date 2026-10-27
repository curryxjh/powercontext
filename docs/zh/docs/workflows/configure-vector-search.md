---
title: 配置向量检索
description: 启用基于 embedding 的 vector 和 hybrid Memory 检索，并验证 Runtime capability。
---

# 配置向量检索

向量检索需要 embedding model、稳定的 profile ID 和该模型的输出 dimension。

## 1. 设置一份 embedding profile

```bash
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_MODEL=provider:embedding-model
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_PROFILE_ID=embedding-model-v1
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_DIMENSION=1024
```

将示例值替换为一个受支持的 provider model、该模型保持稳定的 profile ID，以及其文档给出的输出 dimension。
`POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_NORMALIZATION` 默认值为 `unit`。

输出维度始终要配置，它决定本地向量索引的宽度，并用来校验模型返回的向量。默认还会把这个值作为请求参数 `dimensions` 发给模型。有些 OpenAI 兼容服务不接受该参数，例如硅基流动上的 `BAAI/bge-m3`。这类模型保留文档中的输出维度（bge-m3 为 1024），并关闭发送：

```bash
export POWERCONTEXT_SERVER_INFERENCE_EMBEDDING_SEND_DIMENSIONS=false
```

## 2. 启动 Server

```bash
powercontext server run
```

使用 SQLite 时，PowerContext 会在打开数据库时加载内置 sqlite-vec extension。extension 与当前 platform 或 SQLite build
不兼容时，启动会失败。

## 3. 验证 capability

```bash
powercontext capabilities
```

结果会报告已启用的 search mode。未配置 embedding profile 时，SQLite full-text search 仍可使用。

能力标记只说明 Runtime 已加载向量通道，还需要用一条合成 Source 验证模型调用、索引写入和实际命中。完整的
Source → flush → entry → vector search 验收命令见[启用 Memory 提取与向量搜索](../get-started/configure-models.md)。
其中搜索响应必须包含 `mode: "vector"`、目标 `entry_id`，并且 `matched_by` 包含 `vector`；如果使用 `hybrid`，应把请求
中的 `mode` 改为 `hybrid` 并核对实际返回模式。显式 `vector`/`hybrid` 不会在 Embedding 不可用时静默降级。

如果在已有 Memory 上首次启用 Embedding，先用一条临时 Scope 完成上述闭环，再对真实 Scope 运行受控的重处理/索引流程，
并确认旧 citation 没有变化。不要仅修改 profile ID 或 dimension 来绕过已有向量与模型不匹配的错误。

timeout、batch size、storage 设置和准确默认值见[配置](../operate/configuration.md)。

## 在 SDK 中共享 Embedding 请求

SDK 应用可以包装已有的 `EmbeddingModel`，启用请求合并与有界向量缓存。在同一事件循环的多个调用之间共享
一个包装器，并将其注入 Runtime：

```python
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel
from powercontext.builtin.runtime import open_builtin_contexts

model = CoalescingEmbeddingModel(
    base_model, max_batch_size=64, coalesce_ms=5.0, cache_size=1024
)
async with open_builtin_contexts(config, embedding_model=model) as contexts:
    scope = await contexts.get("project")
    # 通过 scope.artifacts.memory 正常写入和检索 Memory。
```

`max_batch_size` 限制单次底层请求中的不同文本数。`coalesce_ms` 是非负的合并窗口毫秒数；设为零时，
同一轮事件循环中已经可以执行的调用仍可共享请求。`cache_size` 是成功文本向量的 LRU 缓存容量，
设为零关闭已完成结果的缓存，但保留执行中请求的共享。批次上限和缓存容量必须是整数，前者为正数，后者非负。

每个调用仍按原始输入顺序获得向量，并保留重复位置。其 `usage` 对实际等待过的每个不同底层批次只汇总一次，
保留 provider 报告的请求数与 token 数。共享批次可以计入多个调用的 usage，因此不能将这些值视为底层账单的独占分摊。
纯缓存命中的请求数为零；所有相关批次均未报告某种 token 用量时，该字段保持 `None`，否则汇总已知值。

取消一个调用不会取消共享工作。底层失败或向量数量不匹配会使依赖该批次的调用失败，但不会污染缓存，
也不会阻止独立批次完成。失败文本可以重试。区分查询与文档向量的 provider 使用不同的共享请求和缓存身份，
对称模型则在两种操作之间共享向量。

包装器暴露底层模型的 profile。缓存仅属于包装器实例，不持久化，也不跨 worker 进程共享；
包装器生命周期内应保持模型与 profile 配置不变。未使用包装器的应用维持原有行为。
