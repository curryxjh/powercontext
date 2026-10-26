# MiniMax × OceanBase：订单状态筛选的 SDD 上下文

本目录是独立可运行的 Python 3.11+ 样例。任务是在保留原有无筛选行为的同时，为订单列表加入精确的 `status` 筛选。工程资料由嵌入式 seekdb 保存并检索；PowerContext 保存任务进度，供后续进程读取；MiniMax-M3 使用检索所得上下文修改 `sample_app/orders.py`。不需要启动数据库服务或完整 Agent 框架。

## 环境与入口

支持有 `pylibseekdb` wheel 的 macOS 或 Linux；需要 Python 3.11+ 和 `uv`。从仓库根目录执行：

```bash
uv venv minimax/.venv --python 3.11
uv pip install --python minimax/.venv/bin/python -r minimax/requirements.txt
minimax/.venv/bin/python -m minimax.sdd_context ingest --data-dir minimax/.runtime
minimax/.venv/bin/python -m minimax.sdd_context context --data-dir minimax/.runtime --query status
```

固定的直接依赖见 `requirements.txt`：PowerContext 1.2.0、pylibseekdb 1.4.0.post1、PyMySQL 1.2.3、pytest 9.1.1。`ingest` 读取 `manifest.json` 所列的真实规格、代码和测试，将原文及 SHA-256 写入 seekdb。`context` 用 seekdb 全文查询返回匹配文档的路径、类别、原文、摘要和相关度，并加入 PowerContext 已存任务进度。首次运行时 `progress` 为 `null`。

```bash
minimax/.venv/bin/python -m minimax.sdd_context save-state \
  --data-dir minimax/.runtime \
  --completed "已导入规格、代码和测试" \
  --pending "实现筛选并运行测试" \
  --validation "基线功能测试失败，回归测试通过"
minimax/.venv/bin/python -m minimax.sdd_context resume \
  --data-dir minimax/.runtime --query status
```

`save-state` 将已完成、待办和验证结果写入 PowerContext Memory；`resume` 在新进程中读取最新记录，并与当时的 seekdb 查询结果一起输出。每次命令都会重新打开持久化实例。数据仅位于指定的 `--data-dir`，在干净环境从 `ingest` 开始即可重建；重置时删除该目录后重新执行上述命令。`--root` 可指向另一个含有 `minimax/manifest.json` 的工程副本，供规格变更验证。

修改 `specs/order-list.md` 后再次执行 `ingest` 和 `context`，相同路径的内容与摘要会更新；输出不依赖预置答案。查询需要至少一个英文或数字词，本样例使用 `status`，最多返回 12 个匹配文档。

需要用自己的 MiniMax Code 再执行开发任务时，先通过它的 CLI 完成登录，并在待修改的工程副本中运行 `bash minimax/run_agent.sh`。脚本先把当前数据库检索结果和 PowerContext 进度写入指定数据目录的 `context-before.json`，再作为附件交给 `MiniMax-M3`，模型调用记录存为 `agent-run.json`。脚本采用非交互的代码修改权限；它会请求模型再次检查并可能修改 `orders.py`，不属于常规验收必跑命令。

## 验证

```bash
minimax/.venv/bin/python -m minimax.verify > minimax/evidence/replayed-tests.json
minimax/.venv/bin/python -m pytest -q minimax/tests
```

`verify` 在临时目录中用**同一份** `tests/test_orders.py` 分别执行 `evidence/orders-before.py` 与修改后的 `sample_app/orders.py`。输出记录测试文件和两份代码的 SHA-256、命令、退出码及完整日志；修改前目标测试因筛选未实现而失败（退出码 1，1 失败/1 通过），修改后功能与兼容性测试都通过（退出码 0，2 通过）。`test_sdd_context.py` 使用真实 seekdb 和 PowerContext，检查三类来源、规格更新重新导入，以及两个独立进程之间的最新状态复用；全套为 3 个通过。

## 提交资料

| 材料 | 位置 |
| --- | --- |
| 任务、规则与初始资料 | `specs/order-list.md`、`manifest.json`、修改前的 `evidence/orders-before.py` |
| 上下文模块与业务源码 | `sdd_context.py`、`sample_app/orders.py` |
| MiniMax Agent 接入 | `run_agent.sh`、`evidence/minimax-prompt.md` |
| 功能和回归测试 | `tests/test_orders.py`、`tests/test_sdd_context.py` |
| 检索与状态复用记录 | `evidence/context-before.json`、`evidence/context-resumed.json` |
| MiniMax 实际调用结果 | `evidence/minimax-run.json` |
| 代码差异与测试日志 | `evidence/order-change.patch`、`evidence/test-results.json` |
| 结构和技术分工 | `TECHNICAL.md` |

`context-before.json` 包含交给 MiniMax 的完整规格、代码、测试和 PowerContext 初始进度；`minimax-run.json` 记录 `MiniMax-M3` 实际成功的模型调用、模型回复和用量。`context-resumed.json` 是重新打开数据库后生成的结果，Memory revision 从 1 增至 2，代码来源摘要也变为修改后版本。样例和记录不含 API Key。

## 已知限制

这是一个局部开发任务的 CLI 上下文模块：需要显式导入资料，不监控文件变化；manifest 限定三个样例来源；PowerContext 使用本地 SQLite，seekdb 专门承担工程资料及全文检索。状态读取在这个小 Scope 中列出 Memory 并选最新任务记录，适合本样例，不是大型任务库的分页方案。MiniMax 的登录凭据由其 CLI 管理，不属于交付文件。
