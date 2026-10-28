# 忘川当铺

> 忘川河边，一间只收记忆的当铺。你押下一段记忆，掌柜阿忘给你一个愿望；下次再来，他仍然记得你押过什么。

一个用 **Dify Chatflow** 编排、由 **PowerContext** 保存并召回长期记忆的对话小游戏。提交赛道：Dify × OceanBase「Just for Fun」。

## 玩法循环

1. **典当**：你说一段记忆和一个愿望。掌柜估价，并开出当票编号。
2. **记账**：这段记忆以 `wangchuan.pawn` 写入 PowerContext，成为该玩家账本中的一条长期记忆。
3. **重逢**：新开一个对话，你只要提到旧记忆里的人、物或细节，掌柜会先引用原文，再谈这次交易。
4. **查账 / 赎回**：输入「查账」查看未赎当票；输入「赎回 1」停用对应记忆，并留下赎回记录。

Dify 负责对话编排与掌柜人格；PowerContext 负责跨会话存取，二者职责不混。

## 架构

```text
浏览器（Dify Web App）
        │  聊天消息
        ▼
Dify Chatflow「忘川当铺」13 个节点
  ├─ 查账 / 账本 ──────────► 只读账本分支
  ├─ 赎回 N ──────────────► 停用记忆分支
  └─ 其他输入 ─► 召回旧账 ─► 掌柜 LLM ─► 封装记账 ─► 写入当票 ─► 回答
        │  HTTP + JSON
        ▼
FastAPI 适配层（dify/backend，127.0.0.1:8787 或 0.0.0.0:8787）
        │  PowerContext HTTP API
        ▼
PowerContext Server（SQLite + FTS5，127.0.0.1:8000）
```

适配层只做四件事：把 Dify 的 `sys.user_id` 映射成稳定的 PowerContext scope、把账本格式化成掌柜可读的文本、把中文口令翻译成停用记忆的调用、把纯文本结果交还给 Dify。它不复制 PowerContext 的记忆规则，也不替 Dify 做对话生成。

## 目录

| 路径 | 内容 |
| --- | --- |
| `dify/dsl/wangchuan-pawnshop.yml` | 可导入的 Dify Chatflow DSL（version 0.3.1，advanced-chat） |
| `dify/backend/wangchuan/` | FastAPI 适配层源码 |
| `dify/backend/tests/` | 适配层行为测试（7 项） |
| `dify/docs/runbook.md` | 从零启动 PowerContext、适配层与 Dify 的完整步骤 |
| `dify/docs/architecture.md` | 身份映射、记忆格式、当票生命周期与接口说明 |
| `dify/docs/validation.md` | 验收样例：初始状态、输入、步骤、期望、实际证据 |
| `dify/docs/evidence/` | 真实运行产生的端到端记录与 DSL 图回放记录 |
| `dify/scripts/check_dsl.py` | DSL 结构检查（节点、边、变量引用、节点字段） |
| `dify/scripts/replay_flow.py` | 不依赖 Dify 的图执行器：按 DSL 的边和条件跑真实后端 |
| `dify/scripts/verify_e2e.py` | 端到端验收脚本，生成 `docs/evidence/` 下的记录 |
| `dify/scripts/start_backend.sh` | 读取 `.env` 并启动适配层 |

## 快速开始

前置：Python 3.11+，一个可用的 Dify 1.x 实例，以及一个已配置的对话模型。

```bash
# 1. 启动 PowerContext（最小无模型配置，仅用 FTS 记忆）
powercontext server run --env-file /absolute/path/to/pc.env

# 2. 启动适配层
cd dify/backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
cd ..
cp .env.example .env                               # 按需修改 POWERCONTEXT_URL
bash scripts/start_backend.sh

# 3. 两个健康检查都应返回 200
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8787/health
```

`pc.env` 的最小内容：

```dotenv
POWERCONTEXT_HOME=/absolute/path/to/powercontext-data
POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
POWERCONTEXT_SERVER_HTTP_PORT=8000
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false
POWERCONTEXT_SERVER_MCP_ENABLED=false
POWERCONTEXT_SERVER_METRICS_ENABLED=false
```

### 导入 Dify 的顺序

1. **先配置模型**：在 Dify「设置 → 模型供应商」中启用 DeepSeek（官方插件 `langgenius/deepseek` 0.0.26+，模型 `deepseek-v4-flash`），填入你的 API Key；或准备任意兼容的对话模型。DSL 默认节点使用 `langgenius/deepseek/deepseek` + `deepseek-v4-flash`，不含任何密钥。
2. **先启动后端**：PowerContext 与适配层必须在导入后第一次对话前可访问。
3. **再导入 DSL**：Dify 工作室 → 创建空白应用 → 导入 DSL 文件 → 选择 `dify/dsl/wangchuan-pawnshop.yml`。
4. **必要时改地址**：DSL 中 4 个 HTTP 节点默认请求 `http://host.docker.internal:8787`。Dify 源码运行时改为 `http://127.0.0.1:8787`；Linux 上的 Docker 部署需给 `api` 与 `worker` 增加 `extra_hosts: ["host.docker.internal:host-gateway"]`。
5. **打开应用对话**：无需初始化数据，第一位玩家第一次发言时会自动创建其 PowerContext scope 与空账本。

完整步骤、网络说明与故障排查见 [docs/runbook.md](docs/runbook.md)。

## 验收

- 验收样例与逐条期望：[docs/validation.md](docs/validation.md)
- DSL 的 13 个节点均通过 Dify 1.18 工作流运行时（`graphon 0.8.0`）的节点模型校验
- 真实端到端记录（PowerContext scope、条目状态、赎回审计）：[docs/evidence/e2e-verify-20261028094820.md](docs/evidence/e2e-verify-20261028094820.md)
- DSL 图逐节点回放记录：[docs/evidence/graph-replay-20261028.md](docs/evidence/graph-replay-20261028.md)

复现命令（脚本需要 Python 3.11+ 与 `PyYAML`，`verify_e2e.py` 只用标准库）：

```bash
PYTHONIOENCODING=utf-8 python dify/scripts/check_dsl.py
PYTHONIOENCODING=utf-8 python dify/scripts/replay_flow.py \
  --player demo-player \
  --message "我想典当第一次看海的记忆，那天码头有海风，换一次好运。" --verbose
PYTHONIOENCODING=utf-8 python dify/scripts/verify_e2e.py \
  --powercontext-url http://127.0.0.1:8000
```

`replay_flow.py` 会真实执行 DSL 中的 Code、IF-ELSE、HTTP 节点并调用适配层；只有 LLM 节点使用确定性替身，因此它验证的是图结构与接口契约，不替代 Dify 内的模型效果验收。

## PowerContext 在这里做了什么

| 能力 | 调用 | 产生的记录 |
| --- | --- | --- |
| 玩家身份 | `GET /v1/scopes`（按 `external_reference_value` 查询）+ `POST /v1/scopes` | 每个 `sys.user_id` 一个 scope，`kind=wangchuan.player` |
| 典当 | `POST /v1/memory/remember` | `kind=wangchuan.pawn`，文本含当票号、记忆原文、掌柜批注 |
| 跨会话召回 | `POST /v1/memory/search`（`mode=auto`） | 命中旧当票的 `entry_id` / `entry_version_id` |
| 查账 | `POST /v1/memory/entries/list`（`include_inactive=false`） | 读取未赎当票并计算下一张编号 |
| 赎回 | `POST /v1/memory/entries/retire` + 再写一条 `wangchuan.redeem` | 原当票 `state=inactive`，赎回记录保留原文 |

记忆实际存放在 PowerContext 的 SQLite 中；适配层不落任何玩家数据。

## 已知限制

- **中文检索是词面匹配**。最小部署使用 SQLite FTS5 `unicode61`，连续中文词（码头、桂花糕、海风）可命中，但「考试」不会命中「高考」。需要语义召回时，按 PowerContext 文档启用 embedding 与 hybrid 检索即可，适配层无需修改。
- **当票编号只增不减**。赎回 #1 后下一张是 #3，而不是复用 #1；这保证旧当票号永远指向同一段历史。
- **身份依赖浏览器**。Dify Web 的 `sys.user_id` 存在浏览器侧；换浏览器/隐身窗口会被当成新客。用 API 调用时可显式传入稳定的 `user`。
- **适配层不做鉴权**。默认监听 `0.0.0.0` 只为让 Docker 内的 Dify 访问；请只在可信网络运行，或改为 `PAWN_HOST=127.0.0.1` 并让 Dify 走本机回环。
- **LLM 是必需项**。掌柜人格由 Dify LLM 节点生成；没有可用模型时可在节点中换成任意对话模型，或临时替换为固定回复节点。

## 提交材料对照

| 题目要求 | 位置 |
| --- | --- |
| 4.1 Dify DSL 文件 | `dify/dsl/wangchuan-pawnshop.yml` |
| 4.2 运行说明（依赖、启动顺序、导入、网络） | `dify/docs/runbook.md` |
| 4.3 验证样例与运行证据 | `dify/docs/validation.md`、`dify/docs/evidence/` |
| 4.4 自定义后端源码与脚本 | `dify/backend/`、`dify/scripts/`、`dify/docs/architecture.md` |
| 状态数据与记忆初始化方式 | 见本文「快速开始」与 `docs/architecture.md`；无需种子数据，首个请求按玩家惰性创建 scope |
| seekdb / PowerContext 的作用与记录 | 见本文「PowerContext 在这里做了什么」与证据文件中的原始条目 |

## 安全说明

- 仓库中只有占位符，没有真实 API Key、密码或令牌。
- 适配层的环境变量示例不含任何凭据；PowerContext 默认关闭鉴权并只监听回环地址。
- 不要把 `.env`、本地数据库、`__pycache__` 或运行时日志提交到仓库（见 `dify/.gitignore`）。
