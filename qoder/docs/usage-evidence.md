# 真实使用证据

比赛鼓励提交真实使用效果。本文件说明温故如何记录使用、如何导出证据，以及哪些数字可以核验。**不虚构用户、不编造使用时长或反馈。**

## 1. 证据从哪里来

### 1.1 API 使用日志

FastAPI 中间件把每个 `/api/*` 请求追加到 `data/usage.jsonl`（静态资源不计入）。每行是一个 JSON：

```json
{"ts":"2026-10-28T10:15:03+00:00","date":"2026-10-28","method":"POST","path":"/api/learners/l-1a2b3c4d/reviews","pattern":"/api/learners/{slug}/reviews","status":201,"ms":18.42,"learner":"l-1a2b3c4d"}
```

| 字段 | 含义 |
| --- | --- |
| `ts` | UTC 时间 |
| `date` | 按 `WENGU_TIMEZONE` 的本地日期 |
| `method`, `path` | 实际请求 |
| `pattern` | 归一化路由（slug/entry id 被替换） |
| `status`, `ms` | 状态码与耗时 |
| `learner` | 若路径包含学员 slug 则记录 |

不记录请求体、记忆内容、IP 或任何凭据。

查看汇总：

```bash
curl http://127.0.0.1:8010/api/usage?days=14
python scripts/export_usage.py --days 14
python scripts/export_usage.py --days 14 --out docs/usage-summary.json
```

### 1.2 反馈

`POST /api/feedback` 把反馈写入独立的 PowerContext Scope（`kind=feedback`），不混入学员记忆。页面「成长与反馈」可查看；接口：

```bash
curl http://127.0.0.1:8010/api/feedback
```

反馈记录包含评分、文本、角色/称呼（可选）与时间；演示种子中的反馈已明确标注为示例。

### 1.3 PowerContext 侧证据

- `/api/learners/{slug}/memory`：记忆条数、类型、revision、citation。
- `/api/learners/{slug}/changes`：每次修订/删除的操作与原因。
- `/api/learners/{slug}/proof`：实时 `search`、`context.prepare`、source 关联与 `model_requests=0`。
- `scripts/verify_powercontext.py`：从外部只读复核以上事实。

## 2. 当前可以核验什么

| 证据 | 获取方式 | 说明 |
| --- | --- | --- |
| 请求量与活跃天数 | `export_usage.py` 的 `requests_in_window`、`active_days` | 只统计真实发生的 API 请求 |
| 成功写入次数 | `successful_memory_writes` | 2xx 的 POST/PATCH/PUT/DELETE |
| 学员数量 | `learners_observed` | 日志中出现过的 slug |
| 记忆规模与 revision | `/api/usage` 的 memory 汇总 | 来自 PowerContext 统计 |
| 用户反馈 | `/api/feedback` | 原文、评分、时间 |
| 记忆可追溯性 | proof / changes / 记忆中心 | 每条状态都能指回 entry 与 revision |

演示种子写入的 10 张卡、16 条复习等属于**演示数据**，不计入「真实用户效果」。重置 `data/` 后，真实使用日志从零开始。

### 2.1 本机验证记录（2026-10-28）

下列数字来自开发/验收时的真实请求日志与 PowerContext 运行时，用于证明记录链路可用；**它们是本机验证，不是真实用户规模**：

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| API 请求（30 天窗口） | 54 次 | `docs/usage-summary.json` |
| 成功记忆写入（2xx 写请求） | 12 次 | 同上 |
| 活跃天数 | 1 天（2026-10-28） | 同上 |
| 观察到的学员 | `demo` | 同上 |
| 反馈 | 2 条（1 条演示种子 + 1 条本机验证） | `docs/feedback.json` |
| 记忆规模 | 44 条 total / 43 条 active / rev 16 | `docs/verify-output.txt` |
| 模型请求 | 0 | 同上 |

验证流程覆盖：完整复习 7 张卡并生成会话总结、导入 2 张卡片、中文 FTS 检索、记忆详情与 citation、修订（revision +1）、删除（active -1）、提交反馈。截图见 `docs/screenshots/07-11`。

> 反馈中的称呼「林知夏 / 参赛者」沿用演示身份，仅用于走通本机表单，不代表第三方真实用户。

## 3. 提交前的取证步骤

在真实使用一段时间后（至少跨 3 天），执行：

```bash
# 1. 导出使用汇总（不要手工改数字）
python scripts/export_usage.py --days 30 --out docs/usage-summary.json

# 2. 导出反馈
curl http://127.0.0.1:8010/api/feedback > docs/feedback.json

# 3. 保存只读验收输出
python scripts/verify_powercontext.py > docs/verify-output.txt

# 4. 截图
#    - docs/screenshots/11-growth-feedback.png  成长与反馈页（真实请求/写入/记忆条数）
#    - docs/screenshots/09-memory-search.png    记忆中心的 citation 与 revision
#    - docs/screenshots/07-review-summary.png   复习会话总结与下次动作
#    - docs/screenshots/11-growth-feedback.png  反馈列表
```

把截图放入 `docs/screenshots/`，并在下表填写。

### 3.1 真实用户记录（提交前填写）

| 用户（可用化名） | 使用日期 | 使用场景 | 完成的学习动作 | 可核验证据 | 反馈原文（经同意） |
| --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | usage 日志 / 截图 | 待填写 |

填写原则：

- 只记录确实发生过的事；没有的数据留空，不估算成「约 XX 人」。
- 用户身份可用化名，但需能说明来源（同学、同事、社群），并取得展示同意。
- 「节省时间」优先使用用户自述；若使用 `sessions × 15 分钟` 的基线，必须标注为估算方法，而不是实测。

### 3.2 时间节省口径

页面与 `/api/usage` 中的 `estimated_prep_minutes_saved = 会话数 × 15` 是**保守的替代基线**：假设没有工具时，每次复习前需要约 15 分钟整理「今天该复习什么」。它不是实测的用户节省时间，不能当作真实效果宣传。真实效果应来自用户访谈或对照记录。

## 4. 演示数据的边界

- 自动种子与 `seed_demo.py` 写入的学员「林知夏」、笔记、复习、卡点、会话和反馈全部为虚构演示，用于让评审一键看到完整流程。
- 演示数据通过真实 PowerContext 路径写入，因此技术上可验证，但**不代表真实使用量**。
- 提交真实使用证据前，建议先重置 `data/`，再进行真实使用，避免演示数据混入统计；或在文档中明确区分时间窗口。

## 5. 隐私与合规

- 本地优先：数据默认只存在运行机器的 `data/`，不上传。
- 使用日志不记录学习内容与身份信息，仅路由与状态。
- 公网演示前请清理真实用户数据，或使用独立实例与演示学员。
- 反馈展示需取得提交者同意；不提交真实 API Key、密码或其他凭据。
