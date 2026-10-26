# 技术说明

```text
manifest.json → 源文件 → seekdb.project_documents（原文、SHA-256、FULLTEXT）
                                  ↓ SQL MATCH AGAINST
任务查询 → sdd_context.py → 规格、代码、测试来源 + PowerContext Memory 最新进度
                                  ↓
                         MiniMax-M3 → orders.py → pytest
                                  ↓
                   PowerContext Memory 写入验证结果 → 下一进程 resume
```

`python -m minimax.sdd_context` 是调用入口，输入为操作、数据目录和查询词；输出为 JSON。`ingest` 按路径更新资料，`context` 用参数化 SQL 全文检索，保留真实文件路径、原文和摘要。`save-state` 将任务完成项、待办项和测试结果写入 PowerContext 1.2.0 的 Scope Memory；`resume` 再次检索 seekdb，并读取 PowerContext 中最新任务记录来生成后续上下文。状态库与工程资料库分别由 PowerContext SQLite 和嵌入式 seekdb 管理，不共享隐藏的进程内数据。

`run_agent.sh` 将最新上下文作为附件传给 MiniMax Code。MiniMax Code 0.6.2 的 `MiniMax-M3` 模型接收了 `evidence/context-before.json`，只修改订单列表函数。`evidence/minimax-run.json` 保留模型与调用结果，差异见 `evidence/order-change.patch`。测试在修改前后使用相同文件和相同命令；`evidence/test-results.json` 包含各次代码哈希、退出码与结果。更改规格后重新导入会替换 seekdb 同一路径记录，验收测试覆盖了内容和摘要的变化。三份资料的样例检索至多返回 12 条；增量重导入仅改写 manifest 中的条目，适合该固定小样例。
