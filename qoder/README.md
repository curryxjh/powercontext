# 温故 WenGu — 用 PowerContext 做「学习接力」

温故是一个离线优先的学习接力教练：记住你学过什么、卡在哪里、上次为什么停下，下一次打开时直接继续。

它是 2026 Qoder × OceanBase「Build with Qoder」参赛作品。**所有学习状态都保存在 PowerContext 的 Scope / Memory / Source 里，没有第二个业务数据库，也不需要任何模型 API Key。**

- 项目网站：<https://wengu-relay-lq9r998sqe4.qoder.zone>（Qoder Sites，未登录可访问）
- 代码：本仓库 `qoder/` 目录
- 技术栈：Python 3.11+、FastAPI、PowerContext 1.2.0（embedded builtin runtime）、SQLite、无构建前端
- 运行方式：一条命令启动，本机访问 `http://127.0.0.1:8010`

---

## 1. 它解决什么问题

临时抱佛脚时，真正昂贵的不是「再看一遍」，而是：

1. 忘了自己学过什么、哪里没懂；
2. 每次都要重新向工具或同学解释背景；
3. 计划断掉后，不知道从哪里接上；
4. 不知道「记住」这件事本身有没有发生。

温故把学习过程写成可检索、可修订、可追溯的**记忆**，再由一个确定性的教练算法重放出今日计划、断点续学和卡点提醒。记忆不是藏在后台数据库里：在「记忆中心」里，每条画像、卡片、复习、卡点、会话都能看到 PowerContext 的 entry、版本、revision 和 citation，也能直接修改或删除。

## 2. PowerContext 在其中做什么

| 能力 | 在温故中的用法 |
| --- | --- |
| Scope | 每个学习者一个 Scope；反馈写入独立的共享 Scope |
| Memory | 学习画像、知识卡片、复习事件、卡点、学习会话、反馈六类记忆 |
| Source | 粘贴的笔记、单张卡片的答案作为原始资料被捕获，卡片通过 `source_id` 指回来源 |
| 全文检索 | 中文 FTS 检索记忆，例如搜「卡点」「梯度」 |
| `context.prepare` | 「关于温故」页实时组装带 citation 的上下文，证明状态确实来自 PowerContext |
| revise / retire | 修改或遗忘一条记忆会生成新版本与 revision，历史可查 |
| statistics | 记忆条数、来源数、模型请求数（=0）等清点结果直接来自运行时 |

PowerContext 以 `powercontext[builtin]==1.2.0` 内嵌运行，数据库是本地 SQLite 文件。应用进程内没有第二个状态库：页面上的 streak、掌握度、计划顺序，全部由 PowerContext 记忆重放得到。

## 3. 快速开始

需要 Python 3.11+（开发与验证使用 3.12.4）。首次安装依赖需要联网，之后可完全离线使用。

```bash
cd qoder

# Windows PowerShell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py

# macOS / Linux
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python run.py
```

也可以直接使用脚本（会自动创建虚拟环境并安装依赖）：

```bash
./run.sh          # macOS / Linux / Git Bash
.\run.ps1         # Windows PowerShell
```

打开 <http://127.0.0.1:8010>。首次启动会自动写入一个可复现的演示学员「林知夏」；如果已有数据则不会重复写入。

想从空数据开始：

```bash
WENGU_AUTO_SEED=0 python run.py
```

环境变量可以写在 `qoder/.env`（参考 `.env.example`），也可以直接 export。`WENGU_DATA_DIR` 支持相对路径，相对于 `qoder/` 解析。

### 运行验证

服务启动后，另开一个终端：

```bash
python scripts/verify_powercontext.py
```

它会以只读方式通过 HTTP API 检查：PowerContext 版本、Scope、卡片、复习重放、记忆条目、Source 关联、中文全文检索、`0` 次模型请求、`context.prepare` 条目与 citation、revision 历史、Web 首页。全部通过时退出码为 0。

### 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

测试覆盖记录编码、笔记解析、复习调度、计划排序、断点续学、streak、真实内嵌 PowerContext 的读写/检索/修订/删除，以及 FastAPI 的完整学习流程。

## 4. 主要功能

- **今日接力**：根据每天可投入时长生成 3–15 项计划，优先卡点、逾期和遗忘过的卡片，并说明每一项为什么出现。
- **复习流程**：0–3 四档自评。评 0 的卡片 10 分钟后重新出现并记为一次遗忘；其余按 SM-2 风格扩展间隔。
- **断点续学**：用最近一次会话、未解决卡点和最近复习生成「距上次学习 N 天」与下一步动作。
- **笔记导入**：支持 Markdown `##` 标题、`Q:/A:` 问答、普通段落三种结构，自动拆成卡片并保留原笔记为 Source。
- **记忆中心**：浏览、筛选、全文检索所有记忆；查看原始文本、结构化字段、citation、Source 与 revision；支持修改和删除。
- **上下文自证**：「关于温故」页调用 `context.prepare` 展示带 citation 的上下文；「验证脚本」再从外部复核同一组事实。
- **成长与反馈**：真实请求/写入日志、记忆清点、反馈写入独立 Scope。
- **数据可带走**：`GET /api/learners/{slug}/export` 导出该学员的全部记忆。

## 5. 数据与配置

默认数据目录是 `qoder/data/`：

| 文件 | 内容 |
| --- | --- |
| `wengu.db` | PowerContext 内嵌 SQLite 数据库（Scope / Memory / Source / revision） |
| `wengu.db-wal`, `wengu.db-shm` | SQLite WAL 文件 |
| `wengu.scheduler.db` | PowerContext 调度器状态（首次产生调度时创建） |
| `usage.jsonl` | 每个 `/api/*` 请求的本地使用日志，用于真实使用证据 |

常用环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WENGU_HOST` | `127.0.0.1` | 监听地址；容器或局域网演示可设 `0.0.0.0` |
| `WENGU_PORT` | `8010` | 端口 |
| `WENGU_DATA_DIR` | `./data` | 数据目录，相对路径按 `qoder/` 解析 |
| `WENGU_AUTO_SEED` | `1` | 空库时自动写入演示学员 |
| `WENGU_TIMEZONE` | `Asia/Shanghai` | streak 与「今天」的时区 |
| `WENGU_MAX_IMPORT_CHARS` | `120000` | 单次导入上限 |
| `WENGU_MAX_ANSWER_BYTES` | `6000` | 单张卡片答案上限（PowerContext 单条记忆上限 8192 字节） |
| `WENGU_RELOAD` | `0` | 开发时自动重载 |

重置演示数据：停止服务后删除 `qoder/data/`，或运行：

```bash
python scripts/seed_demo.py --force
```

## 6. 项目结构

```
qoder/
├── app/
│   ├── main.py          # FastAPI 路由、中间件、静态页面
│   ├── memory_store.py  # PowerContext 运行时封装：Scope / Memory / Source / context
│   ├── records.py       # 类型化记忆的编码、解码与 8192 字节预算
│   ├── coach.py         # 纯函数：记忆重放、SM-2 调度、计划、断点、统计
│   ├── service.py       # 所有写入学习记忆的业务动作
│   ├── importer.py      # 离线笔记解析
│   ├── seed.py          # 可复现演示学员
│   └── config.py        # 环境配置与 .env 读取
├── web/                 # 无构建的原生 HTML/CSS/JS 前端
├── scripts/
│   ├── verify_powercontext.py  # 只读验收脚本
│   ├── export_usage.py         # 汇总真实使用日志
│   └── seed_demo.py            # 重建演示学员
├── tests/               # pytest：单元 + 内嵌运行时 + HTTP 流程
├── docs/                # 架构、运行手册、验收、Qoder 开发记录、使用证据
├── run.py / run.sh / run.ps1
├── requirements.txt / requirements-dev.txt
└── .env.example
```

## 7. 设计取舍与边界

- **离线、无 Key**：教练逻辑是确定性的，不调用模型；`/api/health` 与 proof 页会显示 `model_requests = 0`。
- **不是第二个数据库**：业务层不维护学员表，只维护记忆编码与重放逻辑；删除一条记忆即改变状态。
- **单实例**：SQLite + 单 worker，适合个人或小班演示；不是多租户 SaaS。
- **无登录**：默认只监听 `127.0.0.1`。公网部署前请加反向代理与访问控制。
- **时间精度**：记忆时间戳精确到秒；同一张卡在同一秒内连续评两次的极端情况下，重放顺序可能不稳定，正常复习流程（评 0 后 10 分钟复现）不受影响。

## 8. 来源与致谢

- 运行时：[PowerContext](https://github.com/oceanbase/powercontext) 1.2.0，Apache-2.0。本项目直接使用其 embedded builtin runtime，未修改其源码。
- 演示学员「林知夏」及其笔记、复习记录均为虚构的演示数据，不对应真实用户。
- 除上述依赖外，未复用其他开源代码或数据集。

## 9. 文档

- [架构与数据流](docs/architecture.md)
- [运行与运维手册](docs/runbook.md)
- [验收与验证样本](docs/validation.md)
- [Qoder 开发记录](docs/qoder-devlog.md)
- [真实使用证据](docs/usage-evidence.md)
