# 验收与验证样本

本文给出可复现的初始数据、输入、操作步骤、预期结果，以及「指定技术确实在工作」的证据。所有命令在 `qoder/` 目录执行。

## 0. 验收环境

- Python 3.11+，实测 3.12.4
- `powercontext[builtin]==1.2.0`
- 默认地址 `http://127.0.0.1:8010`
- 建议从干净数据目录开始：

```bash
# 确认没有服务在写数据库后
rm -rf data

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# 或：. .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
.venv\Scripts\python.exe run.py
```

首次启动会自动写入演示学员。若使用 `WENGU_AUTO_SEED=0`，执行 `POST /api/demo/seed` 或 `python scripts/seed_demo.py`。

## 1. 自动化检查

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

预期：`46 passed`（测试数量会随维护增长，以全绿为准）。测试不读写 `data/`，覆盖：

- 记忆编码/解码、8192 字节预算、UTF-8 截断
- 三种笔记结构与去重
- SM-2 重放、状态、掌握度、计划顺序、断点、streak
- 真实内嵌 PowerContext 的 Scope、写入、中文检索、修订、删除、Source、`context.prepare`
- FastAPI 的学员/卡片/复习/导入/记忆/反馈/演示种子/错误路径

服务启动后运行只读验收：

```bash
python scripts/verify_powercontext.py
```

预期结尾：

```text
Result: 15/15 checks passed
```

如有 `FAIL`，脚本以非 0 退出。

## 2. 初始数据（演示学员）

演示学员「林知夏」，目标「两周后通过机器学习期中考试，重点补概率和线代」，每天 20 分钟，偏好图示 + 生活类比。

种子写入的内容：

| 类型 | 数量 | 说明 |
| --- | --- | --- |
| Source | 2 | 机器学习复习笔记、线代复习笔记 |
| 知识卡片 | 10 | 覆盖概率、线代、优化等主题 |
| 复习事件 | 16 | 分布在最近 11 天，含一次遗忘 |
| 卡点 | 3 | 2 个未解决、1 个已解决 |
| 学习会话 | 4 | 最近一次在昨天，带下次动作 |
| 反馈 | 1 | 明确标注为演示反馈 |

刚种子完成时（以种子运行当天为准）：

- 计划项：7 项
- streak：11 天（截至昨天；今天尚未学习）
- 断点续学：「昨天已经学过了」
- `model_requests`：0

随着继续使用，这些数字会变化；需要恢复时运行 `python scripts/seed_demo.py --force`。

### 2.1 首屏与健康检查

```bash
curl http://127.0.0.1:8010/api/health
```

预期片段：

```json
{
  "status": "ok",
  "powercontext_version": "1.2.0",
  "scopes": 3,
  "learners": 1,
  "app_version": "1.0.0",
  "timezone": "Asia/Shanghai"
}
```

`scopes` 至少为 3（演示学员 + 反馈箱 + PowerContext 自带的 `Default` Scope；有真实学员时会更多）。

```bash
curl http://127.0.0.1:8010/api/bootstrap
```

预期 `demo.available` 为 `true`，`demo.slug` 为 `demo`，`learners` 至少包含 `demo`。

### 2.2 页面检查

打开 <http://127.0.0.1:8010>，确认：

1. 首页显示「今天已经学过了」或「昨天已经学过了」，而不是「第一次见面」。
2. 今日计划有 7 项，首项带有卡点/逾期等理由。
3. 左侧「记忆中心」徽标显示的记录数 > 0。
4. 「成长与反馈」显示最近 7 天活动、streak、记忆 revision。
5. 「关于温故」能加载 `context.prepare` 结果，条目带 citation，且模型请求为 0。

## 3. 验证指定技术：PowerContext 是真实数据源

### 3.1 现场证据接口

```bash
curl "http://127.0.0.1:8010/api/learners/demo/proof?q=%E5%8D%A1%E7%82%B9"
```

预期包含：

- `scope_id`：以 `scp_` 开头
- `memory_revision` ≥ 1
- `inventory.memory_active` > 0、`inventory.sources` ≥ 2、`inventory.model_requests` = 0
- `search.query` 为「卡点」，`hits` 非空，命中项带 `entry_id`、`score`、`matched_by`
- `context.status`（如 `ready`）、`content_bytes` > 0
- `sample_citations` 中每条都有 `entry_id` 与 `version_id`

### 3.2 `context.prepare` 自带引用

`proof.context.content` 中包含 PowerContext 生成的：

```text
BEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1
{ "items": [ { "citation": { "entry_id": "...", ... }, ... } ] }
END_POWERCONTEXT_PREPARED_CONTEXT_V1
```

验收脚本会解析这段 JSON，并验证每个 item 都有 `citation.entry_id`。

### 3.3 revision 历史

```bash
curl http://127.0.0.1:8010/api/learners/demo/changes
```

预期 `revisions` 非空，每项包含 `revision` 与 `changes`（`op`、`entry_id`、原因、前后 version）。

### 3.4 记忆中心

打开「记忆中心」：

- 搜索「卡点」，命中卡点与相关复习记忆；
- 点击任意记忆，能看到：人类可读文本、`§meta§` 结构化字段、`entry_id` / `version_id` / `memory_revision` / citation、关联 Source；
- 修改一条卡片说明并保存，revision +1，详情出现修订记录；
- 点击「删除/遗忘」，该记忆变为 inactive，计划与统计立即变化，但仍能在「全部状态」中查看。

## 4. 输入样本：导入笔记

### 输入

```text
# 概率复习

## 条件概率
在已知事件 B 发生的条件下，事件 A 发生的概率写作 P(A|B)，等于 P(AB)/P(B)。

## 全概率公式
把样本空间按互斥事件划分，用各分支的条件概率加权求和，得到目标事件的概率。
```

API：

```bash
curl -X POST http://127.0.0.1:8010/api/learners/demo/import \
  -H "Content-Type: application/json" \
  -d '{"text":"# 概率复习\n\n## 条件概率\n在已知事件 B 发生的条件下，事件 A 发生的概率写作 P(A|B)，等于 P(AB)/P(B)。\n\n## 全概率公式\n把样本空间按互斥事件划分，用各分支的条件概率加权求和，得到目标事件的概率。","topic":""}'
```

### 预期

- `parsed.title` = `概率复习`
- `parsed.items` = 2
- `created` 长度 = 2（两张知识卡片）
- `source.source_id` 非空；两张卡片的 `meta.source_id` 都指向它
- 记忆中心可看到 1 条新 Source 关联与 2 条 `knowledge` 记忆
- 今日计划出现这两张新卡（若容量允许）

UI 路径：「导入笔记」→ 粘贴上方文本 → 主题留空 → 提交；页面提示识别到 2 个知识点，并跳到知识库。

## 5. 输入样本：复习与遗忘

### 5.1 评 0（忘记）

```bash
# 先取一张卡的 item_id（没有 jq 也能运行）
python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8010/api/learners/demo'))['view']['items'][0]['item_id'])"

curl -X POST http://127.0.0.1:8010/api/learners/demo/reviews \
  -H "Content-Type: application/json" \
  -d '{"item_id":"<item_id>","rating":0,"note":"分不清先验和后验"}'
```

预期：

- `requeue` = `true`
- `message` 提示十分钟后再次出现
- `item.interval_days` = 0
- `struggle` 非空，且写入一条 `struggle` 记忆
- 下一次打开该学员时，该卡在计划中靠前，理由包含「你记录过卡点」与「已逾期/遗忘」

### 5.2 评 2（掌握）

对**另一张卡**（或等待十秒后再评同一张卡，避免同秒排序边界）：

```bash
curl -X POST http://127.0.0.1:8010/api/learners/demo/reviews \
  -H "Content-Type: application/json" \
  -d '{"item_id":"<另一张卡 item_id>","rating":2}'
```

预期：

- `requeue` = `false`
- 首次评 2 的卡片 `interval_days` = 2，`message` 给出下次复习日期
- 记忆中心新增一条 `review`

### 5.3 结束会话

> 将时间换成当前时间即可；间隔 8 分钟会产生 `duration_minutes = 8`。

```bash
curl -X POST http://127.0.0.1:8010/api/learners/demo/sessions \
  -H "Content-Type: application/json" \
  -d '{"session_id":"verify-s1","started_at":"2026-10-28T09:00:00+08:00","ended_at":"2026-10-28T09:08:00+08:00","reviewed":2,"ratings":{"0":1,"2":1}}'
```

预期：

- 返回 `session`，`duration_minutes` = 8
- `next_action` 非空
- 重复提交同一 `session_id` 返回 `duplicate: true`，不再新增记忆
- 首页断点续学更新为本次会话的 `next_action`

## 6. 输入样本：记忆修订与删除

1. 在记忆中心打开一张 `knowledge` 记忆，记下 `entry_id` 与 `memory_revision`。
2. 修改说明并保存。

```bash
curl -X POST http://127.0.0.1:8010/api/learners/demo/memory/<entry_id>/revise \
  -H "Content-Type: application/json" \
  -d '{"human":"【线代】特征值是什么\n---\n满足 Av=λv 的非零向量 v，对应特征值 λ。"}'
```

预期：`record.memory_revision` 比修改前大 1；`changes` 出现一条修订 op；页面显示新文本，原版本仍可通过修订历史追溯。

3. 点击「遗忘」或：

```bash
curl -X POST http://127.0.0.1:8010/api/learners/demo/memory/<entry_id>/retire
```

预期：`record.state` 不再是 `active`；该卡从计划与统计中消失；「全部状态」筛选仍能看到它。

## 7. 输入样本：反馈与真实使用记录

```bash
curl -X POST http://127.0.0.1:8010/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"rating":5,"text":"第一次能在记忆中心直接看到复习记录来自哪条来源。"}'
```

预期：返回 `record.kind` = `feedback`；`GET /api/feedback` 的 `total` 增加；反馈写入独立 Scope，不出现在学员记忆中心。

使用记录：

```bash
python scripts/export_usage.py
```

预期：`requests_in_window`、`successful_memory_writes`、`by_route` 等由 `data/usage.jsonl` 汇总，不出现演示种子之外的虚构数字。

## 8. 错误路径

| 请求 | 预期 |
| --- | --- |
| `GET /api/learners/nobody` | 404，`没有找到这个学习者` |
| `POST /api/feedback {"rating":0}` | 422（Pydantic 校验） |
| `POST /api/learners/demo/reviews {"rating":9}` | 422 |
| 导入「短」 | 400，提示使用 `##` 或 `Q:/A:` |
| `GET /api/learners/demo/memory/mem_missing` | 404，`没有找到这条记忆或资料` |
| 重复 `session_id` | 200，`duplicate: true`，不新增记忆 |

## 9. 端到端实测记录（2026-10-28）

在 Windows 11、Chrome 1440px、Python 3.12、PowerContext 1.2.0 上，从干净数据重新种子后完整走了一遍 UI。以下数字均来自实际运行，不是预置截图。

### 9.1 复习会话

- 起点：10 张卡、16 条复习、7 项计划、streak 11、记忆 rev 5 / 34 条。
- 通过首页「接着学」进入复习，依次翻面并评价 7 张卡；其中一次「忘记」会立即重排到 10 分钟后，其余按 SM-2 风格给出下次日期。
- 会话结束页汇总 7 张已评价、7 次自评、streak 12；「下次先攻」引用用户写下的卡点原文，而不是通用文案。
- 此时记忆 rev 13 / 42 条，新增 7 条 `review` 与 1 条 `session`。
- 截图：`docs/screenshots/05-review.png`、`07-review-summary.png`。

### 9.2 导入、检索与记忆修订/删除

- 在知识库点「导入笔记」，粘贴含两个 `##` 标题的笔记：解析出 2 张知识卡片，页面提示「已拆分导入 2 张知识卡片」；原文保存为 1 份 Source，两张卡片都带 `source_id`。
- 记忆中心搜索「全概率」：返回 9 条命中，模式为 `fts`；右侧 `context.prepare` 现场组装出带 citation 的上下文；底部 revision 历史显示 rev 14。
- 打开导入的「全概率公式」记忆：可见 `§meta§` 结构化字段、`entry_id`、`version_id`、`memory_revision`、citation 和原始资料全文。
- 在详情抽屉中追加一句说明并保存：revision +1，旧版本仍保留在历史中。
- 删除同批导入的「马尔可夫链的平稳分布」：它变为 inactive，有效记忆从 44 降到 43，计划与统计立即收缩，但「全部状态」仍可查到。
- 截图：`08-library-imported.png`、`09-memory-search.png`、`10-memory-detail.png`。

### 9.3 反馈与使用日志

- 在「成长与反馈」提交一条 5 分反馈：提示「谢谢，反馈已写入 PowerContext」，反馈总数从 1 变为 2。
- 该反馈写入独立反馈 Scope，不混入学员记忆；其中「林知夏 / 参赛者」是本机验证用的演示身份，不是真实用户。
- 成长页同时显示真实请求明细、接口聚合、学习会话和记忆清点（模型请求 0）。
- 截图：`11-growth-feedback.png`。

### 9.4 最终复核

```text
pytest: 46 passed
verify_powercontext.py: 15/15 checks passed
11 cards · 23 reviews · memory 44 total / 43 active · rev 16
3 sources · 0 model requests
```

对应证据文件：

| 文件 | 内容 |
| --- | --- |
| `docs/verify-output.txt` | 只读验收脚本的完整输出（15/15） |
| `docs/usage-summary.json` | `export_usage.py` 汇总：54 次请求、12 次成功写入、1 个活跃日 |
| `docs/feedback.json` | `GET /api/feedback` 原始返回（演示反馈 + 本机验证反馈） |
| `docs/screenshots/01-12` | 首页、记忆、关于、成长、复习、知识库、会话总结、导入、检索、详情、反馈、公网站点 |

> 这些是开发/验收期间的本机操作记录，用来说明功能确实跑通；它们**不是**真实用户规模或真实节省时间，真实使用证据的填写方式见 `docs/usage-evidence.md`。

## 10. 验收对照

| 比赛要求 | 本项目对应证据 |
| --- | --- |
| 网站可在未登录/无痕窗口访问 | Qoder Sites 公网站点：<https://wengu-relay-lq9r998sqe4.qoder.zone>；应用本身无登录 |
| 按说明可运行 | 本文第 0–2 节、`README.md`、`docs/runbook.md` |
| Qoder 参与可验证 | `docs/qoder-devlog.md`（对话截图、UID、迭代记录） |
| 指定技术真实使用 | 第 3 节 proof、15 项只读检查、记忆中心 revision/citation、46 项测试 |
| 功能完整与体验 | 首页/复习/导入/记忆中心/成长/关于六页；空状态、错误提示、移动端布局 |
| 工程品质 | 无第二数据库、类型化记忆编码、幂等会话、单元/集成测试、只读验收脚本 |
| 真实使用效果 | `docs/usage-evidence.md` 的记录方法与原始日志；不虚构用户数据 |

## 11. 可复现性说明

- 演示数据通过同一 PowerContext 写入路径生成，不是静态 JSON。
- 种子中的时间相对「运行时刻」计算；跨天运行后，streak 与「距上次学习」会变化，这是真实事件重放的结果。
- 如需获得本文中的初始数字，先 `seed_demo.py --force`，并在同一天完成检查。
- 所有页面文本、记忆内容、时间都在 `data/` 中；重置数据即可回到干净状态。
