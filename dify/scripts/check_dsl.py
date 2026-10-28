"""Structural checks for the 忘川当铺 Dify DSL before importing it.

This does not replace a real import test: Dify still validates provider
credentials, node schemas and runtime behaviour. It catches the mistakes that
make an import fail or a graph silently unreachable.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

TEMPLATE_PATTERN = re.compile(r"\{\{#([^#{}]+)#\}\}")
NODE_OUTPUTS = {
    "start": set(),
    "code": {"body"},
    "if-else": set(),
    "http-request": {"body", "status_code", "headers", "files"},
    "llm": {"text", "usage", "finish_reason"},
    "answer": set(),
}


class Problems:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def report(self, path: Path) -> int:
        if self.items:
            print(f"[FAIL] {path}")
            for item in self.items:
                print(f"  - {item}")
            return 1
        print(f"[OK] {path}")
        return 0


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def check(path: Path) -> int:
    problems = Problems()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        problems.add("DSL 顶层不是对象")
        return problems.report(path)

    if document.get("kind") != "app":
        problems.add("kind 必须是 app")
    if document.get("version") != "0.3.1":
        problems.add(f"version 期望 0.3.1，实际 {document.get('version')!r}")
    app = document.get("app") or {}
    if app.get("mode") != "advanced-chat":
        problems.add("app.mode 必须是 advanced-chat")
    if not app.get("name"):
        problems.add("app.name 不能为空")
    if document.get("dependencies") != []:
        problems.add("当前 DSL 不依赖插件包以外的东西，dependencies 应为 []")

    workflow = document.get("workflow") or {}
    features = workflow.get("features") or {}
    if not str(features.get("opening_statement") or "").strip():
        problems.add("advanced-chat 需要 opening_statement")

    graph = workflow.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        problems.add("graph.nodes 为空")
        return problems.report(path)

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        data = node.get("data") or {}
        node_type = data.get("type")
        if not node_id:
            problems.add("存在没有 id 的节点")
            continue
        if node_id in nodes_by_id:
            problems.add(f"节点 id 重复: {node_id}")
        nodes_by_id[node_id] = node
        if node_type not in NODE_OUTPUTS:
            problems.add(f"节点 {node_id} 的类型 {node_type!r} 不受检查器支持")
        if not data.get("title"):
            problems.add(f"节点 {node_id} 缺少 title")
        if not isinstance(data.get("desc"), str):
            problems.add(f"节点 {node_id} 缺少字符串 desc")

        if node_type == "code":
            code = data.get("code") or ""
            if "def main(" not in code:
                problems.add(f"代码节点 {node_id} 缺少 main 函数")
            outputs = data.get("outputs") or {}
            if not outputs:
                problems.add(f"代码节点 {node_id} 没有声明 outputs")
            declared = [str((variable or {}).get("variable")) for variable in data.get("variables") or []]
            signature = re.search(r"def main\((.*?)\)\s*(?:->\s*[^:]+)?:", code, re.S)
            if signature:
                parameters = [
                    part.split(":")[0].strip()
                    for part in signature.group(1).split(",")
                    if part.strip()
                ]
                if parameters != declared:
                    problems.add(
                        f"代码节点 {node_id} main 参数 {parameters} 与 variables {declared} 不一致"
                    )
        elif node_type == "if-else":
            cases = data.get("cases") or []
            if not cases:
                problems.add(f"条件节点 {node_id} 没有 cases")
            for case in cases:
                if str(case.get("case_id")) not in {"true", "false"}:
                    problems.add(f"条件节点 {node_id} 的 case_id 只能是 true/false")
                if not case.get("conditions"):
                    problems.add(f"条件节点 {node_id} 存在空条件组")
        elif node_type == "http-request":
            if not data.get("url"):
                problems.add(f"HTTP 节点 {node_id} 缺少 url")
            if data.get("method") not in {"get", "post", "put", "patch", "delete", "head"}:
                problems.add(f"HTTP 节点 {node_id} 的 method 非法: {data.get('method')!r}")
            body = data.get("body") or {}
            if body.get("type") == "json" and not body.get("data"):
                problems.add(f"HTTP 节点 {node_id} 的 JSON body 为空")
            if body.get("type") == "json" and isinstance(body.get("data"), list):
                for part in body["data"]:
                    if not isinstance(part, dict) or not part.get("value"):
                        problems.add(f"HTTP 节点 {node_id} 的 JSON body 分段缺少 value")
            retry = data.get("retry_config") or {}
            if retry and "retry_enabled" not in retry:
                problems.add(f"HTTP 节点 {node_id} 的 retry_config 缺少 retry_enabled")
            if not data.get("headers"):
                problems.add(f"HTTP 节点 {node_id} 缺少 headers")
        elif node_type == "llm":
            model = data.get("model") or {}
            for field in ("provider", "name", "mode"):
                if not model.get(field):
                    problems.add(f"LLM 节点 {node_id} 的 model.{field} 为空")
            template = data.get("prompt_template") or []
            if not template:
                problems.add(f"LLM 节点 {node_id} 没有 prompt_template")
            for message in template:
                if not message.get("id"):
                    problems.add(f"LLM 节点 {node_id} 的提示消息缺少 id")
                if message.get("role") not in {"system", "user", "assistant"}:
                    problems.add(f"LLM 节点 {node_id} 的提示消息 role 非法")
        elif node_type == "answer":
            if not str(data.get("answer") or "").strip():
                problems.add(f"回答节点 {node_id} 内容为空")

    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
    incoming: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}
    for edge in edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source not in nodes_by_id:
            problems.add(f"边 {edge.get('id')} 的 source 不存在: {source}")
            continue
        if target not in nodes_by_id:
            problems.add(f"边 {edge.get('id')} 的 target 不存在: {target}")
            continue
        outgoing[source].append(edge)
        incoming[target] += 1
        source_type = (nodes_by_id[source].get("data") or {}).get("type")
        handle = str(edge.get("sourceHandle"))
        if source_type == "if-else" and handle not in {"true", "false"}:
            problems.add(f"条件节点 {source} 的出边 sourceHandle 必须是 true/false，实际 {handle!r}")
        if source_type != "if-else" and handle != "source":
            problems.add(f"节点 {source} 的出边 sourceHandle 应为 source，实际 {handle!r}")
        if edge.get("targetHandle") != "target":
            problems.add(f"边 {edge.get('id')} 的 targetHandle 应为 target")
        data = edge.get("data") or {}
        if data.get("sourceType") != source_type:
            problems.add(f"边 {edge.get('id')} 的 sourceType 与节点类型不一致")
        if data.get("targetType") != (nodes_by_id[target].get("data") or {}).get("type"):
            problems.add(f"边 {edge.get('id')} 的 targetType 与节点类型不一致")

    start_ids = [
        node_id
        for node_id, node in nodes_by_id.items()
        if (node.get("data") or {}).get("type") == "start"
    ]
    if len(start_ids) != 1:
        problems.add(f"必须恰好有一个 start 节点，实际 {len(start_ids)}")
    if start_ids and incoming[start_ids[0]] != 0:
        problems.add("start 节点不应有入边")
    if start_ids:
        reachable = set()
        stack = [start_ids[0]]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(str(edge.get("target")) for edge in outgoing[current])
        for node_id in nodes_by_id:
            if node_id not in reachable:
                problems.add(f"节点 {node_id} 从 start 不可达")

    for node_id, node in nodes_by_id.items():
        node_type = (node.get("data") or {}).get("type")
        if node_type != "answer" and not outgoing[node_id]:
            problems.add(f"节点 {node_id} 没有出边")
        if node_type == "answer" and outgoing[node_id]:
            problems.add(f"回答节点 {node_id} 不应有出边")
        handles = {str(edge.get("sourceHandle")) for edge in outgoing[node_id]}
        if node_type == "if-else" and handles != {"true", "false"}:
            problems.add(f"条件节点 {node_id} 必须同时有 true/false 两条出边，实际 {sorted(handles)}")

    known_targets = set(nodes_by_id) | {"sys"}
    for value in walk_strings(graph):
        for reference in TEMPLATE_PATTERN.findall(value):
            parts = [part.strip() for part in reference.split(".")]
            if len(parts) < 2:
                problems.add(f"模板引用格式错误: {reference!r}")
                continue
            scope, field = parts[0], parts[1]
            if scope == "sys":
                if field not in {"query", "user_id", "conversation_id", "dialogue_count"}:
                    problems.add(f"未知的 sys 变量: {reference!r}")
                continue
            if scope not in known_targets:
                problems.add(f"模板引用了不存在的节点: {reference!r}")
                continue
            node_type = (nodes_by_id[scope].get("data") or {}).get("type")
            if field not in NODE_OUTPUTS.get(node_type, set()):
                problems.add(f"节点 {scope} 没有输出字段 {field!r}: {reference!r}")

    return problems.report(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "dsl" / "wangchuan-pawnshop.yml"),
    )
    args = parser.parse_args()
    return check(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
