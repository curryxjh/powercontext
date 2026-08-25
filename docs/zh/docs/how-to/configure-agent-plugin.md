---
title: 配置 Agent Plugin
description: 在兼容 Agent 中加载可复用的 PowerContext skills 和 MCP configuration。
---

# 配置 Agent Plugin

PowerContext 提供一个可移植的 Agent Plugin package，供能够加载 Agent
Plugin skills 和 MCP configuration 的 Agent 使用。

该 package 位于仓库：

```text
integrations/agent-plugin/powercontext/
```

它包含：

- `plugin.json`：可移植 Agent Plugin metadata。
- `mcp.json`：指向 PowerContext Streamable HTTP endpoint 的 MCP
  configuration。
- `skills/project-context/SKILL.md`：用于 Memory 和 Handoff 工作流的可复用指令。

加载 package 前，先启动 PowerContext Server：

```bash
powercontext server run
```

该 package 默认让兼容 Agent 连接：

```text
http://127.0.0.1:8000/mcp
```

该 package 不负责启动 Server，不新增 MCP tools，也不实现 Runtime 或 Memory
行为。Memory search、writes、revisions、Handoff behavior 和 persistence 仍由
PowerContext Server 及其现有 MCP tools 负责。

认证由加载该 package 的 Agent 或 client 管理。Agent Plugins 1.0.0 不定义远程
MCP server 的可移植 credential-reference 字段，因此仓库中的 `mcp.json` 不包含静态
credentials 或 token placeholders。不要把 bearer token 写入 `mcp.json`。

当某个 Agent 支持 Agent Plugin skills 和 MCP configuration，并且你只需要显式的
Memory 与 Handoff 操作而不是专属 integration 时，可以使用这个 package。
