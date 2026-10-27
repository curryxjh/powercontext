---
title: 解析和检索 PDF 页面
description: 完整采集 PDF 的物理页，并在指定 Scope 内返回可精确回查的 Memory 引用。
---

# 解析和检索 PDF 页面

在 Runtime 依赖之外安装 `powercontext[pdf]`。该可选依赖固定了逐页提取使用的 `pypdf` 版本。
处理完全在本地完成，不依赖在线模型。扫描页需要另行配置 OCR，本解析器仅保留可提取的文本。

```python
from pathlib import Path

from powercontext.sources import SourceDefinitionRegistry, project_source_for_transport
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
)

pages = parse_pdf_document(
    PDFDocumentInput(document_id="年度财报", content=Path("report.pdf").read_bytes())
)
registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
```

解析返回全部物理页组成的 tuple，保持原顺序，页码从一开始。空白页保留，文本为空。
每页携带完整输入字节的 SHA-256 摘要，包括元数据及权限信息。支持以空密码直接读取的权限受限文件。
空文件、非 PDF、无法解密的 PDF 或任意页面的解析失败都抛出 `ValueError`，不会返回部分页面。
文档 ID 不能是空串或纯空白；有意义的首尾空格及中文会被保留。物理页码必须是正整数。

对每页执行 `await registry.resolve(page)`，再通过 `project_source_for_transport(registry, source)`
生成 observation。先调用 `runtime.ingestion.register` 注册
`manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION)`，然后使用 `SubmitSourceObservation` 将各页提交到指定 Scope。
Definition 名称为 `pdf-page`，版本为 `1`，物化方式为 captured。标准文本投影正文为
`document_id + "\n" + page.text`，metadata 恰好包含 `document_id`、`document_sha256` 和 `page_number`。
应通过 Source 处理 pipeline 将投影完整保留为 Memory 证据；仅完成 ingestion 不会自动创建 Memory。

## 回查精确证据

```python
from powercontext.builtin.runtime import GetMemoryEntryRequest
from powercontext.sources.pdf_pages import search_pdf_pages

memory = runtime.memory.for_scope(scope_id)
citations = await search_pdf_pages(memory, "What is net PP&E?", limit=20)
for citation in citations:
    record = await memory.get(GetMemoryEntryRequest(citation=citation))
    # record.entry.sources 指向已经持久化的 PDF 页面。
```

检索只使用传入的 scoped Memory 的公开 search/get API。有限的词法查询扩展覆盖常见财务缩写，
财务报表标题也参与排序。结果是来自真实 Memory 的精确 citation，最多包含 `limit` 个不同的 PDF Source 身份。
没有 PDF 来源的 entry 和同时组合多个 PDF 页面的 entry 不作为精确页面返回；同一页的重复 entry 只占一个结果名额。
不同文档修订具有独立的页面身份。`limit=0` 不访问 Memory，负数或非整数上限、空白问题均被拒绝。

候选检索最多使用 40 个查询变体，每个变体请求至少 100 个候选。引用校验按排序结果逐项读取，
直到获得指定数量的不同页面或候选耗尽，不枚举或改写整个 Memory 集合。实现不使用针对具体文档的答案或证据页清单。
检索质量取决于文档集合和问题；解析完整并不等于已经达到证据页召回指标。

## 持久化身份与修订

Source 身份取决于文档 ID、完整 PDF 摘要和物理页码，长度不超过 256 字符。
短身份保留 `pdf:` 编码；较长身份使用独立的 `pdf-sha256:` 命名空间，对完整身份元组计算摘要，
避免将字面文档 ID 与另一个文档 ID 的摘要混淆。

已有 Source 和精确 citation 保留原名，继续支持读取。对于曾使用有歧义的旧缩短编码的长身份，
重新采集会产生独立命名空间中的身份；既有历史记录不会被自动改名或合并。
应按完整摘要保管原始 PDF 字节，使调用方在新修订入库后仍可定位原修订的物理页。
