# 财报 PDF 解析与证据页检索验证

## 结论与证据范围

赛题采用全部必测项同时满足才得分的规则。平台只返回 `0/50` 时，不能据此定位具体失败项。
本地验证发现了会破坏原子解析与多报告证据召回的可复现缺陷，并用回归测试约束修复。
公开验收通过不等于隐藏质量指标通过：公开脚本检查全页入库、身份与引用有效性，没有分发质量 gold。

## 已复现的失败机制

### 损坏文本流被当成正常页面

`PdfReader(strict=True)` 并不使所有解压行为严格。pypdf 对非法 Flate 数据、缺失末尾校验信息、
错误校验和可能恢复出空字节或部分正文；`extract_text() or ""` 随后把失败伪装成空白页。
未压缩 Form 的文本语法错误也可能在嵌套提取中被忽略。

实现对页面内容流及嵌套 Form 的压缩层进行完整性检查，对 Form 显式解析内容语法。
任意检查失败均由文档解析入口转换为 `ValueError`；tuple 仅在所有页面成功时返回。
合法空白页、空密码权限文件、内容流数组、ASCII85 + Flate 组合和合法 Form 均有正向测试，
避免通过一律拒绝复杂 PDF 来实现失败检查。

基线 `4a9d93d1` 在六种压缩流回归输入上均未抛出异常：非法数据、截断数据、校验和损坏，
分别置于第二页正文和嵌套 Form。对应回归测试均通过修复后的实现。

### 其他公司和年份的报表挤占结果

只按查询变体的排名累加和报表标题加分，会让其他公司或旧年份的标准标题页超过正确报告的证据页。
有效 citation 仍可指向错误文档，因此“返回了 20 条可读取引用”不是召回正确性的证明。

排序现在同时利用标准投影首行文档 ID 与问题中的公司、年份匹配。匹配是加权而非硬过滤，
允许跨公司或跨年份问题；不包含指定财报、问题答案或证据页映射。
公司词的识别覆盖数字和连字符。`margin`、`investment`、`ebitda` 不再作为停用词丢弃。

真实 SQLite 回归建立 5 份合成报告、141 个物理页，包含同公司旧年份和其他公司的大量相似页。
经过完整 PDF 解析、Source 注册、入库、Memory pipeline、关闭重开后检索。
5 个问题共需 6 个证据页，测试要求全部进入前 20，并逐条用公开 `memory.get` 回查页面身份。
基线实现漏掉第一个问题的目标页；修复后 6/6 命中。此数值仅描述自建合成语料，不能外推为官方 Recall@20。

## 赛题要求与测试对应

| 要求 | 本地证据 | 范围限制 |
| --- | --- | --- |
| 全部物理页、顺序、空白页 | 503 页公开 PDF；合成多页及空白页 | 已实际解析原始字节 |
| 文本及表格数字保留 | 已知生成正文的词频多重集合完全相等；Form、组合过滤器 | 官方逐页冻结词数未分发 |
| 解析失败原子性 | 非 PDF、截断文件、损坏后续页、压缩流、嵌套 Form | 针对明确构造的损坏输入 |
| 合法权限 | 无加密、空密码 RC4、空密码 AES；非空密码拒绝 | 本地 pypdf + crypto |
| 身份和标准投影 | 摘要、修订、长 ID、特殊字符、严格页码、resolve/read | 定义仍为 pdf-page v1 |
| 幂等与持久化 | 真实 SQLite、重复提交、关闭重开、历史引用读取 | 无模型、无模拟数据库 |
| 检索上限和去重 | 零上限、非法上限、重复 entry、非 PDF、跨页摘要 | 按真实 Source 身份去重 |
| Scope 隔离 | 不同 Scope 检索不串页 | 真实 scoped Memory |
| 多报告召回 | 141 页合成语料，5 问题、6 证据页全部命中 | 不能替代官方留出集 |
| 官方质量及 Recall@20 | 无可执行的 gold 校验 | 尚不能确认 90%–110%、0.95、0.70 门槛 |

## 执行结果

- `make check`：锁文件、提交钩子、类型检查、30 项 integration manifest 测试全部通过。
- PDF 专项：57 passed。
- Source、Memory、持久化与 Runtime 相关回归：184 passed，13 skipped。
- 13 个跳过项全部要求真实 `POWERCONTEXT_TEST_OCEANBASE_URL`；PDF 专项没有跳过项。
- Python 3.12，pytest 9.0.2、pytest-asyncio 1.4.0、pypdf 6.19.0：公开验收 6 passed，503 页、5 个原始问题。
- 测试运行于 macOS；没有声称复现组织方 Linux 环境或未公开的完整依赖集合。

## 复现命令

仓库安装开发依赖和 PDF extra 后，运行：

```sh
.venv/bin/python -m pytest -q \
  tests/test_pdf_pages.py tests/test_pdf_page_retrieval.py \
  tests/e2e/test_pdf_page_retrieval.py

PYTHONPATH=src:competition PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  uv run --python 3.12 --isolated --no-project \
  --with-editable '.[builtin,pdf]' --with httpx \
  --with pytest==9.0.2 --with pytest-asyncio==1.4.0 \
  python -m pytest -q -s -c competition/pytest.ini --confcutdir=competition \
  competition/challenges/source-03-pdf-retrieval/acceptance

make check
```

产品实现仅使用 PDF 字节、文档 ID、问题及 scoped Memory 的公开接口。
合成正文和预期页号属于测试数据；产品不读取测试、参考答案或判题资产。
再次提交平台时，应使用包含修复的完整 commit SHA；未提交的工作区修改不会出现在远程提交中。
