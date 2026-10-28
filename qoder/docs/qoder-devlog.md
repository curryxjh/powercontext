# Qoder 开发记录

## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 参赛项目 | 温故 WenGu — 用 PowerContext 做学习接力 |
| 开发工具 | Qoder Desktop（Agent 模式） |
| 代码位置 | 本仓库 `qoder/`，分支 `2026-competition-ecosystem` |
| 记录生成日期 | 2026-10-28 |
| Qoder 账号 UID | **【提交前填写：在 Qoder 客户端账号/个人资料中复制 UID】** |

> 本文件是开发过程的文字记录；对话截图/录屏放在 `docs/screenshots/`，与本文一起提交。所有链接指向仓库内实际文件。

## 2. 需求与关键决策

初始需求（用户原意概述）：

- 参加 Qoder × OceanBase「Build with Qoder」比赛；
- 做一个提升学习/研究/工作效率的项目；
- 必须实际使用 seekdb 或 PowerContext 中的至少一个作为核心功能；
- 提供可运行代码、运行说明、验证样本、Qoder 开发记录，并用 Qoder Sites 发布可公开访问的项目网站。

用户明确做出的三个决策：

1. **只使用 PowerContext，不引入 seekdb**：「可以不用seekdb我觉得，光用powercontext即可」。
2. **方向：学习接力教练**，而不是通用笔记或题库。
3. **运行形态：离线优先、无模型 API Key**，教练逻辑确定性可审计。

这三个决策贯穿实现：没有模型调用、没有第二数据库、没有为 seekdb 增加适配层。

## 3. 开发阶段与产物

| 阶段 | 主要工作 | 产物 |
| --- | --- | --- |
| 1. 运行时调研 | 在已安装的 `powercontext 1.2.0` 包中核对 embedded builtin API：`open_builtin_runtime`、Scope、Memory、Source、`context.prepare`、revision、统计 | `app/memory_store.py` 的 API 选择依据 |
| 2. 数据建模 | 设计「六类记忆 + 类型化负载 + 8192 字节预算」，确定无第二数据库、事件重放 | `app/records.py`、`docs/architecture.md` |
| 3. 教练引擎 | 实现 SM-2 风格重放、计划排序、卡点优先、断点续学、streak、统计 | `app/coach.py` |
| 4. 服务层 | 所有写入集中到 service：学员、卡片、导入、复习、会话、卡点、记忆修订/删除、反馈 | `app/service.py` |
| 5. HTTP 与 UI | FastAPI 路由、使用日志中间件、六页无构建前端、记忆中心与 proof 页 | `app/main.py`、`web/` |
| 6. 演示数据 | 通过真实记忆路径写入可复现的 10 卡 / 16 复习 / 4 会话 / 3 卡点（2 未解决）演示学员 | `app/seed.py` |
| 7. 验证 | 浏览器端走通复习、导入、修订、删除、反馈、新建学员；补测试与只读验收脚本 | `tests/`、`scripts/verify_powercontext.py` |
| 8. 文档与发布 | README、运行手册、验收样本、使用证据；构建 Qoder Sites 公网站点 | `README.md`、`docs/`、<https://wengu-relay-lq9r998sqe4.qoder.zone>、`site/` |

## 4. Qoder 参与方式（可核验）

- **代码由 Qoder Agent 在仓库内直接编辑**：每个文件都可在 git 历史中看到；核心文件见上表。
- **运行时以真实安装包为准**：没有凭记忆猜 API；通过读取 `.venv` 中的 `powercontext` 源码确认类型与参数。
- **浏览器内验证**：Qoder 调用浏览器工具实际操作页面，完成复习、导入、记忆修改/删除、新建学员、反馈等流程，并检查控制台错误。
- **自动化验证**：Qoder 编写并运行 pytest（记录见下方）与只读 HTTP 验收脚本。
- **迭代修复**：以下问题均由实际运行/浏览器检查发现，再由 Qoder 定位与修复。

### 4.1 实际迭代记录

| 问题 | 原因 | 修复 |
| --- | --- | --- |
| 首页 streak 只有 1 天，与 11 天活动不符 | 种子复习在「昨天」有断档，今天复习后只能连成 1 天 | 调整种子中一条复习与一次会话到昨天，形成截至昨天的 11 天连续 |
| 首页显示「距上次学习 2 天」，但 streak 包含昨天 | 断点续学只取最近会话，种子会话停在两天前 | 会话改到昨天；1 天文案改为「昨天已经学过了」 |
| 「关于温故」与上下文预览出现 `§meta§ {...}` 原始元数据 | 前端直接展示了 Memory 原文 | 新增 `humanText()` 同时处理真实换行与 JSON 转义形式，在展示层剥离类型化元数据 |
| `context.prepare` 只返回 1 条、约 1006 字节 | `max_bytes` 太小、查询过窄 | 提高到 4000 字节并改用「学习目标、卡点和最近复习」查询，返回 5 条 3780 字节 |
| 新建学员的导入弹窗默认主题是「机器学习」 | 默认值沿用了演示场景 | 默认主题改为空，占位提示「可选，例如：数据结构」 |
| 验收脚本只检查第一条记忆的 `source_id` | 第一版实现假设来源总在首条 | 改为扫描全部记忆，统计关联卡片的来源 |
| 测试中同一秒内对同一张卡评 0 再评 2，间隔偶发为 0 | 记忆时间戳精确到秒，等时事件排序不稳定 | 测试改用两张卡；文档记录该边界，正常 10 分钟复现流程不受影响 |
| 不存在的 Source 抛出 PowerContext 原生异常，未被 API 统一处理 | `get_source` 未捕获 `BaseValueNotFoundError` | 转换为应用内 `RecordNotFound`，统一返回 404 |
| `.env.example` 写了「复制为 .env」，但应用未读取 | 配置只读环境变量 | 增加轻量 `.env` 读取，并让相对数据目录按 `qoder/` 解析 |

### 4.2 验证结果

```text
$ python -m pytest
46 passed

$ python scripts/verify_powercontext.py
PASS  server / powercontext / learner / scope / knowledge / review replay
PASS  memory entries / sources captured / chinese FTS / model requests
PASS  sources / context.prepare / citations / revision history / web app
Result: 15/15 checks passed
```

浏览器端已走通：演示页 → 复习（含评 0 重排）→ 会话总结 → 导入笔记 → 记忆检索 → 记忆详情（citation/raw/source）→ 修订（revision +1）→ 删除（计划收缩）→ 新建学员 → 提交反馈 → 成长页读取真实使用日志。对应产品截图：

| 截图 | 内容 |
| --- | --- |
| `docs/screenshots/01-home.png` | 今日接力：断点续学、计划与理由 |
| `02-memory.png` | 记忆中心：六类记忆、revision、检索与清点 |
| `03-about.png` | 关于温故：`context.prepare` 与 citation、0 次模型请求 |
| `04-growth.png` | 成长与反馈：活动、主题、会话记忆 |
| `05-review.png` | 复习卡片：翻面前的自评说明 |
| `06-library.png` | 知识库：卡片状态、掌握度、下次复习 |
| `07-review-summary.png` | 一次真实复习的会话总结与「下次先攻」 |
| `08-library-imported.png` | 导入两段笔记后新增的卡片与 Source 提示 |
| `09-memory-search.png` | 中文全文检索「全概率」、`context.prepare`、revision 历史 |
| `10-memory-detail.png` | 记忆详情：类型化元数据、entry/version/revision、原始资料、修订入口 |
| `11-growth-feedback.png` | 真实请求日志、接口聚合与反馈记录 |
| `12-site.png` | 已发布的 Qoder Sites 公网站点首页（<https://wengu-relay-lq9r998sqe4.qoder.zone>） |

## 5. 可复核的 Qoder 痕迹

1. **对话截图**：见 `docs/screenshots/` 中的 `qoder-*.png`（提交前补齐）。建议包含：
   - 初始比赛需求与三个决策；
   - Qoder 规划/任务列表；
   - 一次实际的代码修改 diff；
   - 浏览器验证与测试输出；
   - Qoder Sites 发布成功页（公网站点截图见 `12-site.png`）。
2. **账号 UID**：见本文第 1 节，提交前填写。
3. **代码与提交**：`qoder/` 全部文件、`docs/` 文档、测试与脚本。提交信息会说明是比赛实现，而非上游 PowerContext 代码。
4. **运行证据**：`data/usage.jsonl` 与 `/api/usage`、`/api/feedback` 记录的是真实操作，不是为截图编造的静态数据。

## 6. 说明

- 本记录不包含任何真实 API Key、密码或第三方凭据；`.env.example` 全部为占位/默认值。
- 演示学员与演示反馈均为虚构，已在页面与文档中标注；真实使用数据与演示数据分开陈述，见 `docs/usage-evidence.md`。
- 未复用 PowerContext 之外的第三方代码或数据集；PowerContext 的使用与版本见 `README.md` 第 8 节。
