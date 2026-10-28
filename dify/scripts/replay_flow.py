"""Replay the 忘川当铺 DSL graph without a Dify instance.

The script walks the same nodes and edges that Dify imports, executes the Code
nodes for real, evaluates IF/ELSE conditions, and posts to the adapter backend.
The LLM node is replaced by a deterministic stand-in so the replay can run
offline; every other hop is the actual contract used at runtime.

This is a contract check, not a substitute for importing the DSL into Dify.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml

TEMPLATE_PATTERN = re.compile(r"\{\{#([^#{}]+)#\}\}")


class ReplayError(RuntimeError):
    pass


def resolve_selector(selector: list[str], context: dict[str, Any]) -> Any:
    if len(selector) != 2:
        raise ReplayError(f"不支持的变量选择器: {selector!r}")
    node_id, field = selector
    if node_id == "sys":
        return context["sys"].get(field, "")
    node = context.get(node_id)
    if node is None:
        raise ReplayError(f"选择器引用了尚未执行的节点: {selector!r}")
    return node.get(field, "")


def render(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        selector = [part.strip() for part in match.group(1).split(".")]
        value = resolve_selector(selector, context)
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return TEMPLATE_PATTERN.sub(replace, template)


def run_code(data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    inputs = {
        str(variable["variable"]): resolve_selector(list(variable["value_selector"]), context)
        for variable in data.get("variables") or []
    }
    namespace: dict[str, Any] = {}
    exec(compile(data["code"], "<dify-code-node>", "exec"), namespace)  # noqa: S102
    main: Callable[..., dict[str, Any]] = namespace["main"]
    result = main(**inputs)
    declared = set((data.get("outputs") or {}).keys())
    missing = declared - set(result)
    if missing:
        raise ReplayError(f"代码节点 {data['title']!r} 缺少声明输出: {sorted(missing)}")
    return {key: result[key] for key in declared}


def _compare(operator: str, left: Any, right: Any) -> bool:
    text = "" if left is None else str(left)
    if operator == "contains":
        return str(right) in text
    if operator == "not contains":
        return str(right) not in text
    if operator == "start with":
        return text.startswith(str(right))
    if operator == "end with":
        return text.endswith(str(right))
    if operator in {"is", "="}:
        return text == str(right)
    if operator in {"is not", "≠"}:
        return text != str(right)
    if operator == "empty":
        return text == ""
    if operator == "not empty":
        return text != ""
    if operator == "in":
        return text in str(right).split(",")
    if operator == "not in":
        return text not in str(right).split(",")
    if operator in {">", "<", "≥", "≤"}:
        try:
            a, b = float(text), float(right)
        except (TypeError, ValueError) as exc:
            raise ReplayError(f"数值比较失败: {left!r} {operator} {right!r}") from exc
        return {">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b}[operator]
    raise ReplayError(f"不支持的比较运算符: {operator!r}")


def evaluate(data: dict[str, Any], context: dict[str, Any]) -> bool:
    for case in data.get("cases") or []:
        results = [
            _compare(
                str(condition["comparison_operator"]),
                resolve_selector(list(condition["variable_selector"]), context),
                condition.get("value"),
            )
            for condition in case.get("conditions") or []
        ]
        combined = all(results) if case.get("logical_operator") == "and" else any(results)
        if combined:
            return True
    return False


def call_http(data: dict[str, Any], context: dict[str, Any], base_url: str) -> dict[str, Any]:
    url = render(str(data["url"]), context)
    if base_url:
        url = re.sub(r"^https?://[^/]+", base_url.rstrip("/"), url)
    body_config = data.get("body") or {}
    raw_data = body_config.get("data")
    if isinstance(raw_data, list):
        body = "\n".join(str(part.get("value") or "") for part in raw_data if isinstance(part, dict))
    else:
        body = str(raw_data or "")
    body = render(body, context)
    if body_config.get("type") == "json":
        payload = json.loads(body)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    else:
        raw = body.encode("utf-8")
    headers = {}
    for line in str(data.get("headers") or "").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    request = urllib.request.Request(
        url,
        data=raw,
        headers=headers,
        method=str(data.get("method") or "post").upper(),
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        raw_body = response.read().decode("utf-8")
        parsed: Any = json.loads(raw_body) if "json" in content_type else raw_body
        return {
            "body": parsed,
            "status_code": response.status,
            "headers": dict(response.headers),
        }


def stub_llm(data: dict[str, Any], context: dict[str, Any]) -> str:
    system_prompt = ""
    for message in data.get("prompt_template") or []:
        if message.get("role") == "system":
            system_prompt = render(str(message.get("text") or ""), context)
            break
    ledger = ""
    marker = "账本（系统提供，可能为空）："
    if marker in system_prompt:
        ledger = system_prompt.split(marker, 1)[1].strip()
    lines = [line.strip() for line in ledger.splitlines() if line.strip()]
    if lines and "第一次来" not in ledger:
        detail = next((line for line in lines if "当票 #" in line or "典当：" in line), lines[0])
        return f"（替身掌柜）我记得。账本上写着：{detail[:80]}……这回要押什么？"
    return "（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。"


def replay(
    dsl_path: Path,
    player: str,
    message: str,
    base_url: str,
    verbose: bool = False,
) -> str:
    document = yaml.safe_load(dsl_path.read_text(encoding="utf-8"))
    graph = document["workflow"]["graph"]
    nodes = {str(node["id"]): node for node in graph["nodes"]}
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
    for edge in graph["edges"]:
        outgoing[str(edge["source"])].append(edge)

    context: dict[str, Any] = {
        "sys": {"query": message, "user_id": player, "conversation_id": "replay", "dialogue_count": 0}
    }
    current = next(node_id for node_id, node in nodes.items() if node["data"]["type"] == "start")
    steps: list[str] = []

    for _ in range(64):
        node = nodes[current]
        data = node["data"]
        node_type = data["type"]
        steps.append(f"{current}({node_type})")
        if verbose:
            print(f"-> {current} [{node_type}] {data.get('title', '')}")

        if node_type == "start":
            next_handle = "source"
        elif node_type == "code":
            context[current] = run_code(data, context)
            if verbose:
                print(f"   out: {json.dumps(context[current], ensure_ascii=False)[:400]}")
            next_handle = "source"
        elif node_type == "if-else":
            matched = evaluate(data, context)
            if verbose:
                print(f"   condition: {'true' if matched else 'false'}")
            next_handle = "true" if matched else "false"
        elif node_type == "http-request":
            context[current] = call_http(data, context, base_url)
            if verbose:
                body = context[current]["body"]
                preview = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
                print(f"   POST {data['url']} -> {context[current]['status_code']}")
                print(f"   body: {preview[:600]}")
            next_handle = "source"
        elif node_type == "llm":
            context[current] = {"text": stub_llm(data, context)}
            if verbose:
                print(f"   reply: {context[current]['text']}")
            next_handle = "source"
        elif node_type == "answer":
            rendered = render(str(data.get("answer") or ""), context)
            print(f"\n[回答] {rendered}\n")
            print(f"[路径] {' -> '.join(steps)}")
            return rendered
        else:
            raise ReplayError(f"不支持的节点类型: {node_type!r}")

        edges = [edge for edge in outgoing[current] if str(edge.get("sourceHandle")) == next_handle]
        if len(edges) != 1:
            raise ReplayError(f"节点 {current} 的 {next_handle} 出边数量为 {len(edges)}")
        current = str(edges[0]["target"])

    raise ReplayError("图在 64 步内没有到达回答节点")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", default="replay-demo-player", help="模拟 sys.user_id")
    parser.add_argument("--message", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument(
        "--dsl",
        default=str(Path(__file__).resolve().parents[1] / "dsl" / "wangchuan-pawnshop.yml"),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    replay(Path(args.dsl), args.player, args.message, args.base_url, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
