"""Run the 忘川当铺 acceptance scenario and write evidence files.

The checks go through the adapter backend, exactly as Dify does, and then read
the raw PowerContext scope to prove the ledger rows and retirement state exist
outside the adapter's own formatting.

Usage:
    python dify/scripts/verify_e2e.py \
        --backend-url http://127.0.0.1:8787 \
        --powercontext-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence"
EXTERNAL_KIND = os.environ.get("PAWN_EXTERNAL_KIND", "wangchuan.player")


def http_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")
        return json.loads(raw) if "json" in content_type else raw


def post_text(base: str, path: str, payload: dict[str, Any]) -> str:
    result = http_json(base + path, payload=payload)
    if not isinstance(result, str):
        raise AssertionError(f"{path} 期望纯文本响应，实际 {type(result).__name__}")
    return result


class Evidence:
    def __init__(self, backend_url: str, powercontext_url: str, player: str) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.powercontext_url = powercontext_url.rstrip("/")
        self.player = player
        self.started_at = datetime.now(timezone.utc)
        self.steps: list[dict[str, Any]] = []
        self.scope_id: str | None = None
        self.raw_entries: list[dict[str, Any]] = []

    def step(self, label: str, request: str, expected: str, actual: str, passed: bool) -> None:
        self.steps.append(
            {
                "label": label,
                "request": request,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
        )
        print(f"[{'PASS' if passed else 'FAIL'}] {label}")

    def check(self, label: str, request: str, expected: str, actual: str, conditions: list[bool]) -> None:
        self.step(label, request, expected, actual, all(conditions))

    def render_markdown(self) -> str:
        lines = [
            "# 忘川当铺 · 端到端验收记录",
            "",
            f"- 运行时间：{self.started_at.isoformat(timespec='seconds')}",
            f"- Dify 适配层：`{self.backend_url}`",
            f"- PowerContext：`{self.powercontext_url}`",
            f"- 玩家标识（相当于 Dify 的 `sys.user_id`）：`{self.player}`",
        ]
        if self.scope_id:
            lines.append(f"- PowerContext scope：`{self.scope_id}`")
        lines += ["", "## 验收步骤", ""]
        for index, step in enumerate(self.steps, start=1):
            lines += [
                f"### {index}. {step['label']}",
                "",
                f"- 请求：{step['request']}",
                f"- 期望：{step['expected']}",
                "- 实际：",
                "",
                "```text",
                str(step["actual"]).strip(),
                "```",
                "",
                f"- 结果：{'PASS' if step['passed'] else 'FAIL'}",
                "",
            ]
        if self.raw_entries:
            lines += ["## PowerContext 原始记录", ""]
            for entry in self.raw_entries:
                lines += [
                    f"- `{entry.get('kind')}` · state=`{entry.get('state')}` · entry=`{entry.get('citation', {}).get('entry_id')}`",
                    "",
                    "```text",
                    str(entry.get("text", "")),
                    "```",
                    "",
                ]
        passed = all(step["passed"] for step in self.steps)
        lines += ["## 结论", "", f"全部 {len(self.steps)} 个步骤：{'通过' if passed else '存在失败'}。", ""]
        return "\n".join(lines)


def find_scope(powercontext_url: str, player: str, token: str | None) -> str | None:
    query = urllib.parse.urlencode(
        {"query": player, "query_field": "external_reference_value", "limit": 100}
    )
    page = http_json(f"{powercontext_url}/v1/scopes?{query}", token=token)
    for item in page.get("items") or []:
        for reference in item.get("external_references") or []:
            if reference.get("kind") == EXTERNAL_KIND and reference.get("value") == player:
                return str(item["scope_id"])
    return None


def collect_raw_entries(
    powercontext_url: str, scope_id: str, token: str | None
) -> list[dict[str, Any]]:
    payload = http_json(
        f"{powercontext_url}/v1/memory/entries/list",
        payload={"scope_id": scope_id, "include_inactive": True},
        token=token,
    )
    entries = list(payload.get("entries") or [])
    entries.sort(key=lambda entry: (str(entry.get("kind")), str(entry.get("text"))))
    return entries


def run(backend_url: str, powercontext_url: str, player: str, token: str | None) -> Evidence:
    evidence = Evidence(backend_url, powercontext_url, player)
    first_memory = "第一次看海，码头有海风，回来买了桂花糕。想换一次好运。"
    second_memory = "加班到凌晨三点，听见楼下便利店卷帘门响。想换一夜好眠。"

    health = http_json(f"{backend_url}/health")
    evidence.check(
        "适配层与 PowerContext 就绪",
        "GET /health",
        "status=ok 且 powercontext=ready",
        json.dumps(health, ensure_ascii=False),
        [health.get("status") == "ok", health.get("powercontext") == "ready"],
    )

    fresh = post_text(
        backend_url, "/v1/session/context", {"player_id": player, "message": "我第一次来，想押点东西。"}
    )
    evidence.check(
        "新玩家第一次进店",
        "POST /v1/session/context",
        "说明账本为空，下一张当票为 #1",
        fresh,
        ["第一次来" in fresh, "#1" in fresh],
    )

    ticket_one = post_text(
        backend_url,
        "/v1/session/turn",
        {"player_id": player, "message": first_memory, "reply": "海风咸，桂花糕甜，这段记忆我收了。当票拿好。"},
    )
    evidence.check(
        "典当第一段记忆",
        "POST /v1/session/turn",
        "返回当票编号 1",
        ticket_one,
        [ticket_one.strip() == "1"],
    )

    ticket_two = post_text(
        backend_url,
        "/v1/session/turn",
        {"player_id": player, "message": second_memory, "reply": "凌晨三点的卷帘门，比梦还响。这张当票你收好。"},
    )
    evidence.check(
        "典当第二段记忆",
        "POST /v1/session/turn",
        "返回当票编号 2（编号跨会话继续）",
        ticket_two,
        [ticket_two.strip() == "2"],
    )

    recall = post_text(
        backend_url,
        "/v1/session/context",
        {"player_id": player, "message": "今天又闻到海风，想起码头和桂花糕。"},
    )
    evidence.check(
        "新会话召回旧账",
        "POST /v1/session/context（模拟新对话）",
        "识别老客，召回含码头、桂花糕的当票，并给出下一张编号 #3",
        recall,
        ["老客" in recall, "码头" in recall, "桂花糕" in recall, "#3" in recall],
    )

    ledger = post_text(backend_url, "/v1/session/ledger", {"player_id": player})
    evidence.check(
        "查账",
        "POST /v1/session/ledger",
        "未赎当票 2 笔，#1 与 #2 都在",
        ledger,
        ["2 笔" in ledger, "#1" in ledger, "#2" in ledger],
    )

    redeemed = post_text(backend_url, "/v1/session/redeem", {"player_id": player, "message": "赎回 1"})
    evidence.check(
        "赎回第一张当票",
        "POST /v1/session/redeem",
        "返还记忆原文，并提示还剩 1 笔",
        redeemed,
        ["第 1 号当票" in redeemed, "码头" in redeemed, "还剩 1" in redeemed],
    )

    ledger_after = post_text(backend_url, "/v1/session/ledger", {"player_id": player})
    evidence.check(
        "赎回后的账本",
        "POST /v1/session/ledger",
        "只剩 #2，#1 不再出现在未赎列表",
        ledger_after,
        ["1 笔" in ledger_after, "#2" in ledger_after, "#1" not in ledger_after],
    )

    recall_after = post_text(
        backend_url,
        "/v1/session/context",
        {"player_id": player, "message": "我好像还押过一段凌晨的记忆。"},
    )
    evidence.check(
        "赎回后仍记得老客身份",
        "POST /v1/session/context",
        "说明是老客、账本只剩未赎记录，下一张为 #3",
        recall_after,
        ["老客" in recall_after, "#3" in recall_after, "第一次来" not in recall_after],
    )

    try:
        scope_id = find_scope(powercontext_url, player, token)
    except (urllib.error.URLError, TimeoutError) as exc:
        evidence.step(
            "PowerContext 原始记录",
            "GET /v1/scopes",
            "按 external_reference 找到玩家 scope",
            f"无法直接访问 {powercontext_url}: {exc}",
            False,
        )
        return evidence

    evidence.check(
        "PowerContext scope 映射",
        "GET /v1/scopes?query_field=external_reference_value",
        f"存在 kind={EXTERNAL_KIND} 的 scope",
        json.dumps({"scope_id": scope_id}, ensure_ascii=False),
        [scope_id is not None],
    )
    if scope_id:
        evidence.scope_id = scope_id
        entries = collect_raw_entries(powercontext_url, scope_id, token)
        evidence.raw_entries = entries
        pawns = [entry for entry in entries if entry.get("kind") == "wangchuan.pawn"]
        redemptions = [entry for entry in entries if entry.get("kind") == "wangchuan.redeem"]
        inactive_pawns = [entry for entry in pawns if entry.get("state") == "inactive"]
        evidence.check(
            "PowerContext 条目状态",
            "POST /v1/memory/entries/list?include_inactive=true",
            "两条典当记录，其中 #1 已停用，并存在赎回记录",
            json.dumps(
                {
                    "pawns": len(pawns),
                    "inactive_pawns": len(inactive_pawns),
                    "redemptions": len(redemptions),
                },
                ensure_ascii=False,
            ),
            [len(pawns) == 2, len(inactive_pawns) == 1, len(redemptions) == 1],
        )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default=os.environ.get("PAWN_BACKEND_URL", "http://127.0.0.1:8787"))
    parser.add_argument(
        "--powercontext-url",
        default=os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--powercontext-token", default=os.environ.get("POWERCONTEXT_TOKEN") or None)
    parser.add_argument("--player", default=None)
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    args = parser.parse_args()

    player = args.player or "verify-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    evidence = run(args.backend_url, args.powercontext_url, player, args.powercontext_token)

    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stem = f"e2e-{player}"
    markdown_path = evidence_dir / f"{stem}.md"
    markdown_path.write_text(evidence.render_markdown(), encoding="utf-8")
    json_path = evidence_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(
            {
                "player": evidence.player,
                "scope_id": evidence.scope_id,
                "backend_url": evidence.backend_url,
                "powercontext_url": evidence.powercontext_url,
                "started_at": evidence.started_at.isoformat(),
                "steps": evidence.steps,
                "raw_entries": evidence.raw_entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n证据已写入 {markdown_path}")
    print(f"结构化结果 {json_path}")
    return 0 if all(step["passed"] for step in evidence.steps) else 1


if __name__ == "__main__":
    sys.exit(main())
