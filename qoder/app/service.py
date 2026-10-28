"""Application services: the only place that writes learner memories."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from .coach import (
    RATING_LABELS,
    build_learner_view,
    find_next_action,
    load_timezone,
    parse_state,
    public_item,
    build_item_states,
)
from .config import Settings
from .importer import parse_notes
from .memory_store import MemoryStore, RecordNotFound
from .records import (
    clip_utf8,
    knowledge_human,
    parse_iso,
    split_knowledge_human,
    to_iso,
    utcnow,
)


class ValidationError(ValueError):
    pass


def _require_text(value: str | None, field: str, *, maximum: int = 4000) -> str:
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{field}不能为空")
    if len(text) > maximum:
        raise ValidationError(f"{field}过长（最多 {maximum} 字）")
    return text


def _minutes(value: Any, default: int = 20) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(5, min(120, parsed))


def _rating(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError("rating 必须是 0-3 的整数") from error
    if parsed not in RATING_LABELS:
        raise ValidationError("rating 必须是 0-3 的整数")
    return parsed


def _find_knowledge(records: list[Any], item_id: str) -> Any:
    for record in records:
        if record.kind == "knowledge" and record.state == "active" and record.meta.get("id") == item_id:
            return record
    raise RecordNotFound(item_id)


def _find_by_entry(records: list[Any], entry_id: str) -> Any:
    for record in records:
        if record.entry_id == entry_id:
            return record
    raise RecordNotFound(entry_id)


async def create_learner(
    store: MemoryStore,
    settings: Settings,
    *,
    name: str,
    goal: str,
    daily_minutes: int,
    style: str,
    slug: str | None = None,
) -> dict[str, Any]:
    clean_name = _require_text(name, "名字", maximum=60)
    clean_goal = _require_text(goal, "学习目标", maximum=500)
    minutes = _minutes(daily_minutes)
    clean_style = (style or settings.default_style).strip()[:80] or settings.default_style
    clean_slug = slug or f"l-{uuid.uuid4().hex[:8]}"
    scope = await store.ensure_learner_scope(clean_slug, clean_name, clean_goal)
    existing = await store.get_profile(scope.scope_id)
    if existing is None:
        await store.write_profile(
            scope.scope_id,
            name=clean_name,
            goal=clean_goal,
            daily_minutes=minutes,
            style=clean_style,
        )
    return {
        "slug": clean_slug,
        "name": clean_name,
        "goal": clean_goal,
        "scope_id": scope.scope_id,
        "daily_minutes": minutes,
        "style": clean_style,
    }


async def update_profile(
    store: MemoryStore,
    settings: Settings,
    scope: Any,
    *,
    name: str,
    goal: str,
    daily_minutes: int,
    style: str,
) -> dict[str, Any]:
    clean_name = _require_text(name, "名字", maximum=60)
    clean_goal = _require_text(goal, "学习目标", maximum=500)
    minutes = _minutes(daily_minutes)
    clean_style = (style or settings.default_style).strip()[:80] or settings.default_style
    await store.update_learner_scope(scope, name=clean_name, goal=clean_goal)
    profile = await store.get_profile(scope.scope_id)
    await store.write_profile(
        scope.scope_id,
        name=clean_name,
        goal=clean_goal,
        daily_minutes=minutes,
        style=clean_style,
        revise_entry_id=profile["record"].entry_id if profile else None,
    )
    return {
        "name": clean_name,
        "goal": clean_goal,
        "daily_minutes": minutes,
        "style": clean_style,
    }


async def learner_data(
    store: MemoryStore,
    settings: Settings,
    slug: str,
    *,
    include_early: bool = False,
    max_items: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    scope = await store.require_scope(slug)
    records, revision = await store.list_records(scope.scope_id)
    inventory = await store.inventory(scope.scope_id)
    state = parse_state(
        records,
        fallback_name=scope.title,
        fallback_goal=scope.summary,
        default_minutes=settings.default_daily_minutes,
        default_style=settings.default_style,
    )
    view = build_learner_view(
        state,
        inventory=inventory,
        memory_revision=revision,
        now=now or utcnow(),
        tz=load_timezone(settings.timezone),
        include_early=include_early,
        max_items=max_items,
    )
    return {
        "scope": {
            "slug": slug,
            "scope_id": scope.scope_id,
            "title": scope.title,
            "summary": scope.summary,
            "version": scope.version,
        },
        "records": records,
        "state": state,
        "view": view,
    }


async def add_knowledge(
    store: MemoryStore,
    settings: Settings,
    scope: Any,
    *,
    topic: str,
    prompt: str,
    answer: str,
    source_title: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_topic = (_require_text(topic, "主题", maximum=40)).strip()
    clean_prompt = _require_text(prompt, "问题/概念", maximum=200)
    clean_answer = _require_text(answer, "答案/说明", maximum=4000)
    clean_answer = clip_utf8(clean_answer, settings.max_answer_bytes)
    moment = now or utcnow()
    source = await store.capture_source(
        scope.scope_id,
        content=clean_answer,
        metadata={
            "title": (source_title or clean_prompt)[:120],
            "topic": clean_topic,
            "kind": "card",
        },
    )
    item_id = f"k_{uuid.uuid4().hex[:12]}"
    meta = {
        "id": item_id,
        "topic": clean_topic,
        "prompt": clean_prompt,
        "source_id": source["source_id"],
        "source_title": (source_title or clean_prompt)[:120],
        "at": to_iso(moment),
    }
    record = await store.append(
        scope.scope_id,
        "knowledge",
        knowledge_human(clean_topic, clean_prompt, clean_answer),
        meta,
    )
    return {
        "item": {
            "item_id": item_id,
            "entry_id": record.entry_id,
            "topic": clean_topic,
            "prompt": clean_prompt,
            "answer": clean_answer,
            "source_id": source["source_id"],
            "created_at": to_iso(moment),
        },
        "source": source,
        "record": record.public(),
    }


async def import_notes(
    store: MemoryStore,
    settings: Settings,
    scope: Any,
    *,
    text: str,
    default_topic: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if len(text) > settings.max_import_chars:
        raise ValidationError(f"一次最多导入 {settings.max_import_chars} 个字符，请分批导入")
    parsed = parse_notes(text, default_topic, max_answer_bytes=settings.max_answer_bytes)
    if not parsed.items:
        raise ValidationError(parsed.warnings[0] if parsed.warnings else "没有识别到知识点")
    moment = now or utcnow()
    source = await store.capture_source(
        scope.scope_id,
        content=text,
        metadata={
            "title": parsed.title[:120],
            "topic": parsed.topic[:120],
            "kind": "import",
            "items": len(parsed.items),
        },
    )
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for item in parsed.items:
        item_id = f"k_{uuid.uuid4().hex[:12]}"
        entries.append(
            (
                "knowledge",
                knowledge_human(item.topic, item.prompt, item.answer),
                {
                    "id": item_id,
                    "topic": item.topic,
                    "prompt": item.prompt,
                    "source_id": source["source_id"],
                    "source_title": parsed.title[:120],
                    "at": to_iso(moment),
                },
            )
        )
    created = await store.append_many(scope.scope_id, entries)
    return {
        "source": source,
        "parsed": {
            "topic": parsed.topic,
            "title": parsed.title,
            "items": len(parsed.items),
            "warnings": parsed.warnings,
        },
        "created": [record.public() for record in created],
    }


async def record_review(
    store: MemoryStore,
    settings: Settings,
    scope: Any,
    *,
    item_id: str,
    rating: int,
    note: str = "",
    session_id: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_rating = _rating(rating)
    clean_note = (note or "").strip()[:500]
    moment = now or utcnow()
    records, _ = await store.list_records(scope.scope_id)
    knowledge = _find_knowledge(records, item_id)
    prompt = str(knowledge.meta.get("prompt") or split_knowledge_human(knowledge.human)[0])
    label = RATING_LABELS[clean_rating]
    human = f"复习「{prompt}」，自评{label}。"
    if clean_note:
        human += f"卡点：{clean_note}"
    review_meta = {
        "id": f"r_{uuid.uuid4().hex[:12]}",
        "item_id": item_id,
        "rating": clean_rating,
        "note": clean_note,
        "at": to_iso(moment),
        "session_id": session_id or f"s_{uuid.uuid4().hex[:10]}",
    }
    review_record = await store.append(scope.scope_id, "review", human, review_meta)

    struggle_record = None
    if clean_rating <= 1:
        struggle_text = clean_note or (
            "复习时完全忘记，需要重新建立记忆。" if clean_rating == 0 else "复习时自评模糊，还没说清具体原因。"
        )
        existing = [
            record
            for record in records
            if record.kind == "struggle"
            and record.state == "active"
            and record.meta.get("item_id") == item_id
            and record.meta.get("status") == "open"
            and str(record.meta.get("text") or "").strip() == struggle_text
        ]
        if not existing:
            struggle_record = await store.append(
                scope.scope_id,
                "struggle",
                f"卡点：{struggle_text}\n来自「{prompt}」的复习。",
                {
                    "id": f"st_{uuid.uuid4().hex[:12]}",
                    "item_id": item_id,
                    "text": struggle_text,
                    "status": "open",
                    "at": to_iso(moment),
                },
            )

    refreshed, _ = await store.list_records(scope.scope_id)
    state = parse_state(
        refreshed,
        fallback_name=scope.title,
        fallback_goal=scope.summary,
        default_minutes=settings.default_daily_minutes,
        default_style=settings.default_style,
    )
    item_states = build_item_states(state)
    current = next((entry for entry in item_states if entry.item.item_id == item_id), None)
    public = public_item(current, moment) if current else None
    if current is None:
        message = f"已记录：{label}。"
    elif current.interval_days > 0:
        message = f"已记住：{label}。下次 {to_iso(current.due_at)[:10]} 复习。"
    else:
        message = f"已记录：{label}。十分钟后这张卡会再出现。"
    return {
        "review": review_record.public(),
        "struggle": struggle_record.public() if struggle_record else None,
        "item": public,
        "message": message,
        "requeue": clean_rating == 0,
    }


async def finish_session(
    store: MemoryStore,
    settings: Settings,
    scope: Any,
    *,
    session_id: str,
    started_at: str,
    ended_at: str,
    reviewed: int,
    ratings: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_session = _require_text(session_id, "session_id", maximum=120)
    start = parse_iso(started_at) or utcnow()
    end = parse_iso(ended_at) or utcnow()
    if end < start:
        start, end = end, start
    count = max(0, min(200, int(reviewed or 0)))
    rating_counts = {str(key): int(value) for key, value in (ratings or {}).items() if str(key) in {"0", "1", "2", "3"}}

    records, _ = await store.list_records(scope.scope_id)
    existing = [
        record
        for record in records
        if record.kind == "session" and record.state == "active" and record.meta.get("session_id") == clean_session
    ]
    if existing:
        return {"session": existing[0].public(), "duplicate": True}

    state = parse_state(
        records,
        fallback_name=scope.title,
        fallback_goal=scope.summary,
        default_minutes=settings.default_daily_minutes,
        default_style=settings.default_style,
    )
    session_reviews = [review for review in state.reviews if review.session_id == clean_session]
    topics = sorted({_prompt_topic(state, review.item_id) for review in session_reviews})
    item_states = build_item_states(state)
    next_action = find_next_action(state, item_states, now or utcnow())
    duration = max(0, int((end - start).total_seconds() // 60))
    parts = " / ".join(f"{RATING_LABELS[int(key)]} {value}" for key, value in sorted(rating_counts.items()))
    topics_text = "、".join(topic for topic in topics if topic) or "本次内容"
    human = (
        f"本次复习 {count} 项"
        + (f"（{parts}）" if parts else "")
        + f"，涉及{topics_text}。下次先攻：{next_action.rstrip('。')}。"
    )
    meta = {
        "id": f"se_{uuid.uuid4().hex[:12]}",
        "session_id": clean_session,
        "started_at": to_iso(start),
        "ended_at": to_iso(end),
        "reviewed": count,
        "ratings": rating_counts,
        "topics": [topic for topic in topics if topic],
        "next_action": next_action,
        "duration_minutes": duration,
        "at": to_iso(end),
    }
    record = await store.append(scope.scope_id, "session", human, meta)
    return {
        "session": record.public(),
        "next_action": next_action,
        "duration_minutes": duration,
        "duplicate": False,
    }


def _prompt_topic(state: Any, item_id: str) -> str:
    for item in state.items:
        if item.item_id == item_id:
            return item.topic
    return ""


async def resolve_struggle(
    store: MemoryStore,
    scope: Any,
    entry_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    records, _ = await store.list_records(scope.scope_id)
    record = _find_by_entry(records, entry_id)
    if record.kind != "struggle":
        raise ValidationError("只能解决卡点记忆")
    meta = dict(record.meta)
    if meta.get("status") == "resolved":
        return {"record": record.public(), "already": True}
    meta["status"] = "resolved"
    meta["resolved_at"] = to_iso(now or utcnow())
    human = record.human
    if "（已解决）" not in human:
        human = human.rstrip() + "（已解决）"
    updated = await store.revise(
        scope.scope_id,
        entry_id,
        kind="struggle",
        human=human,
        meta=meta,
        reason="learner marked struggle resolved",
    )
    return {"record": updated.public(), "already": False}


async def revise_memory(
    store: MemoryStore,
    scope: Any,
    entry_id: str,
    *,
    human: str,
    reason: str = "learner edited memory",
) -> dict[str, Any]:
    records, _ = await store.list_records(scope.scope_id)
    record = _find_by_entry(records, entry_id)
    if record.kind == "profile":
        raise ValidationError("学习画像请到设置页修改")
    clean = _require_text(human, "记忆内容", maximum=6000)
    meta = dict(record.meta)
    meta["edited_at"] = to_iso(utcnow())
    if record.kind == "knowledge":
        first_line, _ = split_knowledge_human(clean)
        prefix = str(meta.get("topic") or "")
        marker = f"【{prefix}】" if prefix else ""
        prompt = first_line[len(marker) :] if marker and first_line.startswith(marker) else first_line
        meta["prompt"] = prompt[:200]
    updated = await store.revise(
        scope.scope_id,
        entry_id,
        kind=record.kind,
        human=clean,
        meta=meta,
        reason=reason,
    )
    return updated.public(include_raw=True)


async def retire_memory(store: MemoryStore, scope: Any, entry_id: str) -> dict[str, Any]:
    updated = await store.retire(scope.scope_id, entry_id, reason="learner forgot memory")
    return updated.public(include_raw=True)


async def add_feedback(
    store: MemoryStore,
    *,
    rating: int,
    text: str,
    role: str = "",
    name: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        score = int(rating)
    except (TypeError, ValueError) as error:
        raise ValidationError("评分必须是 1-5") from error
    if score < 1 or score > 5:
        raise ValidationError("评分必须是 1-5")
    clean = _require_text(text, "反馈内容", maximum=1000)
    moment = now or utcnow()
    scope = await store.ensure_feedback_scope()
    human = f"反馈（{score}/5）：{clean}"
    record = await store.append(
        scope.scope_id,
        "feedback",
        human,
        {
            "id": f"f_{uuid.uuid4().hex[:12]}",
            "rating": score,
            "text": clean,
            "role": (role or "").strip()[:40],
            "name": (name or "").strip()[:40],
            "at": to_iso(moment),
        },
    )
    return record.public()


async def list_feedback(store: MemoryStore) -> list[dict[str, Any]]:
    scope = await store.find_scope("inbox", "wengu_feedback")
    if scope is None:
        return []
    records, _ = await store.list_records(scope.scope_id)
    feedback = [record.public() for record in records if record.kind == "feedback" and record.state == "active"]
    feedback.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return feedback
