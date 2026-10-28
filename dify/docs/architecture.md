# 忘川当铺 · 架构与数据设计

## 1. 组件边界

| 组件 | 职责 | 不负责 |
| --- | --- | --- |
| Dify Chatflow | 识别口令、编排分支、生成掌柜人格回复、展示回答 | 持久化玩家记忆、解释记忆状态 |
| FastAPI 适配层 | 玩家身份映射、PowerContext 调用、账本文本化、口令解析 | 生成对话、复制记忆检索算法 |
| PowerContext Server | scope 与记忆条目的持久化、FTS/混合检索、条目停用与版本 | 玩家会话、当票语义、对话人格 |

这样划分的原因是：Dify 的强项是对话与分支，PowerContext 的强项是长期记忆与检索。适配层只翻译两者之间的协议，避免把记忆规则写进 Dify 的提示词或 Code 节点。

## 2. 请求路径

### 2.1 普通典当

```text
start
  └─ pack（Code：把 sys.user_id + sys.query 编成 JSON）
      └─ route_ledger（IF/ELSE：含「查账」或「账本」？）
          └─ false ─► route_redeem（IF/ELSE：含「赎回」？）
              └─ false ─► context_http（POST /v1/session/context）
                  └─ keeper_llm（system prompt 注入账本文本）
                      └─ pack_turn（Code：追加掌柜回复）
                          └─ turn_http（POST /v1/session/turn）
                              └─ main_answer（正文 + 当票编号）
```

适配层在 `/v1/session/context` 中：

1. 按 `sys.user_id` 找到或创建 PowerContext scope。
2. 调 `entries/list` 读取全部条目（含已停用，用于判断是否老客）。
3. 调 `memory/search` 召回与本次输入相关的旧账。
4. 计算下一张当票号，拼成掌柜可读的纯文本。

在 `/v1/session/turn` 中：

1. 计算下一张当票号。
2. 以 `kind=wangchuan.pawn` 写入 `当票 #N｜典当：…｜掌柜批注：…`。
3. 把当票号作为纯文本返回，Dify 直接拼进回答末尾。

### 2.2 查账

```text
route_ledger true ─► ledger_http（POST /v1/session/ledger）─► ledger_answer
```

只读，不写记忆。列表来自 `entries/list` 的 active 条目，按当票号升序。

### 2.3 赎回

```text
route_redeem true ─► redeem_http（POST /v1/session/redeem）─► redeem_answer
```

1. 从口令里解析当票号（`赎回 1`、`赎回 #1` 均可）。
2. 在 active 当票中找到对应条目。
3. 调 `entries/retire`，用该条目的 citation 精确停用。
4. 再写一条 `kind=wangchuan.redeem` 的审计记忆，保留原记忆原文。
5. 返回叙事文本与剩余未赎数量。

赎回审计写入失败不会回滚已完成的停用，也不会让玩家看到半截交易：异常只记录日志，赎回结果仍按已停用的状态返回。

## 3. 身份映射

| 层 | 标识 | 说明 |
| --- | --- | --- |
| Dify | `sys.user_id` | Web 端由浏览器持久化；同一浏览器的新对话仍是同一玩家 |
| 适配层请求 | `player_id` | 必填，最长 256；空值由 DSL 的 Code 节点回退为 `guest` |
| PowerContext scope | `external_references[]` | `{"kind": "wangchuan.player", "value": "<player_id>"}` |
| PowerContext scope 标题 | 展示用 | `忘川当铺 · 玩家 <前 8 位>` |

scope 创建是幂等的：先按外部引用查询；不存在才创建，并带 `idempotency_key=wangchuan-scope-<sha256(player_id)[:40]>`。并发创建收到 409 时重新查询，不会为同一玩家产生两个 scope。

## 4. 记忆数据

### 4.1 条目类型

| `kind` | 何时写入 | 文本格式 | 状态 |
| --- | --- | --- | --- |
| `wangchuan.pawn` | 每次普通典当 | `当票 #N｜典当：<记忆>｜掌柜批注：<回复>` | 初始 `active`，赎回后 `inactive` |
| `wangchuan.redeem` | 每次赎回成功后 | `赎回当票 #N｜原典当：<记忆>｜掌柜批注：<回复>` | `active`（审计记录） |

单段记忆与批注各截断到 420 字符，避免一次对话写入过长文本；账本展示时再按 90 字符截断。完整的玩家输入仍保留在 Dify 的会话消息中。

### 4.2 当票编号

`next_ticket = max(所有条目文本中出现的「当票 #N」) + 1`，包括已停用的当票和赎回审计。因此：

- 编号跨会话、跨进程重启保持递增；
- 赎回 #1 后，下一张是 #3（若已有 #2）；
- 旧当票号永远指向同一段历史，不会因回收而复用。

### 4.3 状态转换

```text
(不存在) --turn--> active --retire--> inactive
                      │
                      └── 同时写入 redeem 审计（active）
```

- `entries/list(include_inactive=false)`：只返回未赎当票，用于查账。
- `entries/list(include_inactive=true)`：同时返回历史，用于判断老客、计算下一张编号。
- `memory/search`：适配层只保留 active 当票的检索命中；赎回审计虽然本身是 active 条目，但不会被当作旧账原文引用。

### 4.4 初始化

没有种子数据，也不需要建表脚本：

1. 第一位玩家第一次发言时，适配层按外部引用创建 scope。
2. 第一次典当写入第一条 `wangchuan.pawn`。
3. 所有状态都在 PowerContext 的 SQLite 数据库中；适配层重启不丢失。

清空演示数据的方式：换一个 `sys.user_id`（新浏览器/隐身窗口），或按 PowerContext 的方式停用该 scope 下的条目；不要直接改 SQLite 文件。

## 5. 接口

### 5.1 适配层

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/health` | — | `{"status":"ok","powercontext":"ready"}`；PowerContext 不可达时为 `degraded` |
| POST | `/v1/session/context` | `{player_id, message}` | 纯文本账本上下文 |
| POST | `/v1/session/turn` | `{player_id, message, reply}` | 纯文本当票号，例如 `3` |
| POST | `/v1/session/ledger` | `{player_id}` | 纯文本账本 |
| POST | `/v1/session/redeem` | `{player_id, message}` | 纯文本赎回叙事 |

PowerContext 不可达返回 502；请求体缺字段由 FastAPI 返回 422；`turn` 的 `message`/`reply` 为空返回 400。赎回口令不完整或编号不存在时返回 200 的纯文本提示，Dify 可直接展示给玩家。

### 5.2 PowerContext

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/v1/scopes?query=<player>&query_field=external_reference_value` | 查找玩家 scope |
| POST | `/v1/scopes` | 幂等创建 scope |
| POST | `/v1/memory/remember` | 写入当票或赎回审计 |
| POST | `/v1/memory/search` | `mode=auto` 召回旧账 |
| POST | `/v1/memory/entries/list` | 读取账本（可含停用条目） |
| POST | `/v1/memory/entries/retire` | 按 citation 停用当票 |
| GET | `/health/ready` | 适配层健康检查 |

## 6. 检索行为

最小部署只启用 SQLite FTS5：

- tokenizer 为 `unicode61`，对连续中文片段按词面匹配；
- 「码头」「桂花糕」「海风」能命中；
- 「考试」不会命中「高考」，因为二者没有共同的词面 token；
- 搜索无候选时返回空列表，账本读取路径不受影响。

需要语义召回时，在 PowerContext 侧配置 embedding 模型与对应 profile；适配层仍然调用同一个 `/v1/memory/search`，无需修改 Dify DSL 或后端代码。

## 7. 失败与恢复

| 场景 | 行为 |
| --- | --- |
| PowerContext 暂时不可达 | 适配层返回 502，Dify 展示错误；不写入半条记忆 |
| scope 创建并发冲突 | 409 后按外部引用重查，复用已有 scope |
| 赎回口令没有编号 | 200 纯文本提示「赎回需要报上当票编号」并附当前账本 |
| 赎回不存在的当票 | 200 纯文本提示该编号不在未赎列表，并附当前账本 |
| 赎回审计写入失败 | 只记录日志；已完成的停用不回滚，玩家仍得到成功叙事 |
| 重复点击/重试 | `turn` 没有幂等键，重试会新增一张当票；演示时应避免重复提交 |

## 8. 安全边界

- DSL 与文档中只有占位符，不含真实密钥。
- PowerContext 默认关闭鉴权并只监听 `127.0.0.1`，不直接暴露给 Dify 容器。
- 适配层是唯一对外入口，默认不鉴权；只在可信网络使用，或改为回环监听并由 Dify 源码实例访问。
- 适配层不记录玩家原文到日志，只透传与格式化。
