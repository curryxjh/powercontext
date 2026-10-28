# 架构与数据流

本文说明温故如何把「学习状态」完全寄托在 PowerContext 上，以及教练逻辑如何从记忆中重放出来。目标读者是评审与后续维护者。

## 1. 总览

```text
浏览器（web/，原生 JS）
        │  fetch /api/*
        ▼
FastAPI（app/main.py，单 worker）
        │  所有业务写入
        ▼
app/service.py  ──────────────┐
        │                     │
        │ 读写记忆             │ 纯函数重放
        ▼                     ▼
MemoryStore（app/memory_store.py）   coach.py
        │                     ▲
        ▼                     │
PowerContext embedded runtime ──┘
  Scope / Memory / Source / revision
        │
        ▼
data/wengu.db（SQLite + WAL）
```

进程内只有一个长期状态源：PowerContext。`service.py` 负责把用户动作翻译成记忆写入；`coach.py` 负责把记忆读回学习状态；HTTP 层只做校验与编排。没有学员表、卡片表或复习表。

启动过程（`app/main.py` 的 lifespan）：

1. `Settings.from_env()` 解析配置（含 `qoder/.env`）。
2. `MemoryStore.start()` 打开 `open_builtin_runtime(BuiltinConfig(database=SQLiteConfig(...)), scheduler_path=...)`。
3. 若 `WENGU_AUTO_SEED=1` 且没有任何学习者，写入演示学员。
4. 退出时关闭运行时上下文。

## 2. Scope 模型

| Scope | 外部引用 | 内容 |
| --- | --- | --- |
| 学习者 | `kind=wengu_learner, value=<slug>` | 该学员的全部记忆与来源 |
| 反馈箱 | `kind=wengu_feedback, value=inbox` | 所有使用反馈 |

- `ensure_learner_scope()` 使用 `idempotency_key="wengu:learner:<slug>"`，重复调用返回同一个 Scope。
- Scope 的 `title` 保存显示名，`summary` 保存学习目标；改名/改目标会更新 Scope 并修订画像记忆。
- 学习者 slug 由服务端生成（`l-` + 8 位十六进制），或演示学员固定为 `demo`。
- 反馈单独成 Scope，避免混入某个学员的记忆与检索结果。

## 3. 记忆类型与编码

PowerContext 的 Memory entry 是带 `kind` 的自由文本（单条上限 8192 字节）。温故在可读文本后追加一个类型化负载：

```text
复习「梯度下降是什么」，自评掌握。
§meta§ {"v":1,"t":"review","id":"r_9f...","item_id":"k_2a...","rating":2,"note":"","at":"2026-10-28T09:12:00+00:00","session_id":"s_4c..."}
```

- 标记：`META_MARKER = "\n§meta§ "`；`SCHEMA_VERSION = 1`。
- 编码时先计算元数据字节数，再用 `clip_utf8` 截断人类文本，保证整条不超过 8192 字节且不劈开 UTF-8 码点。
- 解码时若没有标记、JSON 损坏或旧版本数据，则返回纯文本与空元数据，记忆仍可显示与检索。
- UI 统一用 `humanText()` 去掉 `§meta§` 之后的部分，因此用户只看到自然语言。

六类记忆及其关键字段：

| kind | 人类文本示例 | 元数据 |
| --- | --- | --- |
| `profile` | 我是林知夏。学习目标：… | `name`, `goal`, `daily_minutes`, `style`, `at` |
| `knowledge` | 【线代】特征值是什么\n---\n… | `id`, `topic`, `prompt`, `answer`, `source_id`, `source_title`, `at` |
| `review` | 复习「…」，自评掌握。 | `id`, `item_id`, `rating`, `note`, `session_id`, `at` |
| `struggle` | 卡点：…\n来自「…」的复习。 | `id`, `item_id`, `text`, `status`, `at`, `resolved_at?` |
| `session` | 本次复习 7 项（…），涉及…。 | `id`, `session_id`, `started_at`, `ended_at`, `reviewed`, `ratings`, `topics`, `next_action`, `duration_minutes`, `at` |
| `feedback` | 反馈（5/5）：… | `id`, `rating`, `text`, `role`, `name`, `at` |

知识卡片的答案同时被捕获为 Source（`kind="card"`），导入笔记则整段捕获为 Source（`kind="import"`）；卡片的 `source_id` 指回它。这样「卡片从哪来」不是口头承诺，而是可查询的数据关联。

## 4. 从记忆重放到学习状态

`coach.parse_state(records, ...)` 只读取活跃记忆，按类型构建：

1. **画像**：取 `at` 最新的 `profile`；没有则用 Scope 的标题/摘要与默认值兜底。
2. **知识卡片**：以 `meta.id` 为稳定 item_id（缺失时退回 entry_id）；prompt/answer 优先取元数据，再退回解析人类文本。
3. **复习事件**：必须能关联到卡片，按时间排序。
4. **卡点**：必须能关联到卡片；`status` 为 `open` / `resolved`。
5. **会话**：按 `ended_at` 排序，保存下次动作、评分分布、主题与时长。

随后 `build_item_states()` 为每张卡重放复习历史，得到 ease、间隔、遗忘次数、到期时间、掌握度与状态。页面上的每个数字都来自这一步，没有缓存状态。

### 4.1 调度（SM-2 风格，确定性）

常量：`INITIAL_EASE=2.5`、`MIN_EASE=1.3`、`MAX_EASE=2.8`、`MAX_INTERVAL_DAYS=180`、`REQUEUE_MINUTES=10`。

对一张卡按时间重放每条复习：

- 评 0（忘记）：`interval=0`，`ease=max(1.3, ease-0.2)`，`lapses+=1`，`due=review.at+10min`。
- 评 1/2/3 且此前 `interval=0`：间隔取 `1/2/4` 天。
- 否则：间隔乘以 `1.15 / ease / ease*1.3`，四舍五入并封顶 180 天。
- ease 随后调整 `-0.15 / 0 / +0.1`，并夹在 `[1.3, 2.8]`。

状态：无复习为 `new`；最近一次 ≤1、间隔 0 或 <3 天为 `learning`；间隔 ≥21 天且最近 ≥2 为 `mastered`；其余 `review`。

掌握度：最近三次评分的加权质量（0/0.35/0.75/1）占 55 分，间隔（封顶 30 天）占 45 分，再按遗忘次数每次扣 4 分，夹在 0–100。

### 4.2 今日计划

- 容量：`round(每日分钟 / 1.8)`，限制在 3–15；可由请求参数覆盖。
- 只取 `due_at <= now` 的卡；新卡最多占约 40%。
- 排序键：有未解决卡点优先 → 逾期天数多优先 → 遗忘次数多优先 → 上次评分低优先 → 掌握度低优先 → 创建时间早优先。
- 按主题交错（round-robin），避免一科连续刷屏。
- `include_early=true` 时用最近到期的未来卡片填满剩余容量。
- 每项附带 `reasons`（卡点/新知识/逾期/遗忘/上次自评），因此计划可解释。
- 没有卡片、没有到期项、提前复习等空状态都有明确文案。

### 4.3 断点续学

以最近一次会话的 `ended_at` 为基准（没有会话则用最近复习）：

- 0 天：「今天已经学过了」；1 天：「昨天已经学过了」；N 天：「距上次学习 N 天」。
- 正文优先使用上次会话的 `next_action`，其次是最新未解决卡点，再次是最近复习。
- 返回最近三个未解决卡点，供首页与教练记忆展示。

### 4.4 统计与 streak

- 按配置时区把复习时间映射为本地日期。
- `streak = max(截至今天的连续天数, 截至昨天的连续天数)`，因此今天还没学不会立刻清零。
- `streak_recent` 是截至最近一个有复习日期的连续天数。
- `activity_7d` 固定输出最近 7 天（含 0 值），前端直接绘制。
- `estimated_prep_minutes_saved = 会话数 × 15`，这是保守的「人工整理计划」基线，不是虚构的使用时长。

## 5. 写入、修订与删除

- `append()` / `append_many()` 在 `asyncio.Lock` 内写入；`append_many` 通过写入前后的 entry id 差集返回新建记录。导入 80 张卡只产生一次批量写入。
- `revise()` 要求当前活跃记录的精确 citation，PowerContext 生成新版本，revision 递增；记录保留同一个 `entry_id`。
- `retire()` 将记忆移出活跃集合（仍可用 `include_inactive` 查看），用于「遗忘」和演示数据重置。
- `finish_session()` 以 `session_id` 去重，重复提交返回已有会话。
- `resolve_struggle()` 修订卡点元数据 `status=resolved`，不删除历史。
- `revise_memory()` 禁止直接修改画像（应走设置页），其余类型允许修改。

## 6. 检索、上下文与证明

- `search()` 调用 PowerContext 中文全文检索（`mode="auto"`），命中结果附带完整记录、分数与匹配方式。
- `prepare_context(query, max_bytes)` 调用 `context.prepare`；返回内容包含 PowerContext 生成的引用与 `BEGIN/END_POWERCONTEXT_PREPARED_CONTEXT_V1` 包裹的条目 JSON。
- `scripts/verify_powercontext.py` 从外部解析该 JSON，校验每个条目都有 `citation.entry_id`，并交叉检查 revision、记忆类型、Source 关联与 `model_requests=0`。
- `proof` 接口同时返回 scope_id、revision、inventory、search、context、前五条 citation 与运行时健康信息，作为「页面状态真的来自 PowerContext」的现场证据。
- `changes()` 返回最近 revision 及每次增删改的 operation、entry/version 与原因，用于记忆详情页的历史展示。

## 7. 一致性、并发与限制

- **单进程单 worker**：SQLite 适合单实例；`run.py` 固定 `workers=1`。
- **写锁**：MemoryStore 内的锁只保护本进程写入；不要用多进程同时写同一数据目录。
- **时间精度**：记忆时间戳精确到秒。同一张卡在同一秒内连续两次评分时，排序可能不确定；正常复习流程不会这样操作，测试也用不同卡片规避该边界。
- **无鉴权**：默认绑定 `127.0.0.1`。公网部署必须放在带认证的反向代理之后。
- **无模型依赖**：没有 embedding、生成或 rerank 请求，因此中文检索依赖 SQLite FTS 能力；`model_requests` 始终为 0。
- **容量**：单条记忆 8192 字节；单次导入 120k 字符、最多 80 张卡；答案默认截断到 6000 字节。这些限制在 UI 与 API 中均有提示。
- **升级**：`requirements.txt` 固定 `powercontext[builtin]==1.2.0`；升级前需重新验证 `open_builtin_runtime` 与 `MemoryEntryInput` 等 API。

## 8. 为什么没有第二个数据库

如果把学员状态复制到业务表，页面就会有两个真相：记忆改了，表和页面可能没改；删除记忆也无法真正遗忘。温故选择：

1. PowerContext 是唯一真相；
2. 其余都是纯函数投影（`parse_state → build_*`）；
3. 任何状态变化都必须先产生记忆写入（或修订/删除）；
4. 页面、导出、proof、验证脚本读取同一组记忆。

代价是每次读页面都要重放记忆。当前数据规模（几十到几百条）下开销可忽略；如果未来增长，可以在进程内做只读缓存，但仍以 revision 失效，而不是引入第二真相。
