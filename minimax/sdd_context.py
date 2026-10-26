"""Build task context from seekdb documents and persisted PowerContext progress."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pylibseekdb
import pymysql
from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, RememberMemoryRequest, open_builtin_runtime
from powercontext.builtin.scope import ScopeDraft

TASK_ID = "orderstatus2026"
DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def _documents(data_dir: Path, operation: str, *, root: Path, query: str = "") -> list[dict[str, Any]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    instance = pylibseekdb.open(str(data_dir / "seekdb"))
    try:
        connection = pymysql.connect(database="test", **instance.connection_options())
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS project_documents (
                        path VARCHAR(255) PRIMARY KEY,
                        category VARCHAR(16) NOT NULL,
                        content TEXT NOT NULL,
                        sha256 CHAR(64) NOT NULL,
                        FULLTEXT KEY document_text (content)
                    )
                    """
                )
                if operation == "ingest":
                    manifest = json.loads((root / "minimax/manifest.json").read_text(encoding="utf-8"))
                    result = []
                    for item in manifest["documents"]:
                        path = item["path"]
                        source = (root / path).resolve()
                        if not source.is_relative_to(root.resolve()) or not source.is_file():
                            raise ValueError(f"Invalid document path: {path}")
                        content = source.read_text(encoding="utf-8")
                        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                        cursor.execute(
                            """
                            INSERT INTO project_documents (path, category, content, sha256)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                category = VALUES(category), content = VALUES(content), sha256 = VALUES(sha256)
                            """,
                            (path, item["category"], content, digest),
                        )
                        result.append({"path": path, "category": item["category"], "sha256": digest})
                    connection.commit()
                    return result

                terms = re.findall(r"[a-zA-Z0-9_]+", query)
                if not terms:
                    raise ValueError("A query with at least one word is required")
                expression = " ".join("+" + term for term in terms)
                cursor.execute(
                    """
                    SELECT path, category, content, sha256,
                           MATCH(content) AGAINST (%s IN BOOLEAN MODE) AS relevance
                    FROM project_documents
                    WHERE MATCH(content) AGAINST (%s IN BOOLEAN MODE)
                    ORDER BY relevance DESC, path
                    LIMIT 12
                    """,
                    (expression, expression),
                )
                return [
                    {"path": path, "category": category, "content": content, "sha256": digest, "score": float(score)}
                    for path, category, content, digest, score in cursor.fetchall()
                ]
            finally:
                cursor.close()
        finally:
            connection.close()
    finally:
        instance.close()


async def _progress(data_dir: Path, record: dict[str, str] | None = None) -> dict[str, Any] | None:
    config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{data_dir / 'powercontext.db'}"))
    async with open_builtin_runtime(config, scheduler_path=data_dir / "scheduler.db") as runtime:
        if runtime.scopes is None:
            raise RuntimeError("PowerContext scope registry is unavailable")
        scope = await runtime.scopes.create(
            ScopeDraft(title="Order listing", summary="SDD task progress", idempotency_key="minimax-order-list")
        )
        memory = runtime.memory.for_scope(scope.scope_id)
        if record is not None:
            text = TASK_ID + " " + json.dumps(record, ensure_ascii=False, sort_keys=True)
            saved = await memory.remember(
                RememberMemoryRequest(entries=(MemoryEntryInput(kind="outcome", text=text),))
            )
            return {
                "scope_id": scope.scope_id,
                "memory_ref": saved.memory_ref.model_dump(mode="json"),
                "record": record,
            }
        page = await memory.list()
        candidates = [item.entry for item in page.entries if item.entry.text.startswith(TASK_ID + " ")]
        if not candidates:
            return None
        latest = max(candidates, key=lambda entry: entry.created_in_revision)
        return {
            "scope_id": scope.scope_id,
            "memory_ref": page.memory_ref.model_dump(mode="json") if page.memory_ref else None,
            "entry_id": latest.entry_id,
            "record": json.loads(latest.text[len(TASK_ID) + 1 :]),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("ingest", "context", "save-state", "resume"))
    parser.add_argument("--data-dir", type=Path, required=True, help="Persisted local seekdb and PowerContext directory")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Repository root containing minimax/manifest.json")
    parser.add_argument("--query", default="status", help="Task terms for seekdb full-text retrieval")
    parser.add_argument("--completed", default="")
    parser.add_argument("--pending", default="")
    parser.add_argument("--validation", default="")
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    if args.operation == "ingest":
        result: Any = {"database": "seekdb", "indexed": _documents(data_dir, "ingest", root=args.root.resolve())}
    elif args.operation == "save-state":
        if not args.completed and not args.pending and not args.validation:
            parser.error("save-state requires at least one progress field")
        result = asyncio.run(
            _progress(
                data_dir,
                {"completed": args.completed, "pending": args.pending, "validation": args.validation},
            )
        )
    else:
        documents = _documents(data_dir, "query", root=args.root.resolve(), query=args.query)
        progress = asyncio.run(_progress(data_dir))
        result = {"task": TASK_ID, "query": args.query, "documents": documents, "progress": progress}
        if args.operation == "resume" and progress is None:
            raise RuntimeError("No saved PowerContext state for this task")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
