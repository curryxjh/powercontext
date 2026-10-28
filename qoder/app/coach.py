"""Deterministic study coach: replay memory into state, plan and continuity.

Nothing here calls a language model. The "intelligence" is:

* an SM-2 style schedule replayed from the learner's review memories;
* weak-point memories that lift an item to the front of the queue;
* profile memories that bound session length and phrasing;
* session memories that produce the "where you left off" handoff.

Keeping this layer pure makes it easy to test and easy for a reviewer to audit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .records import MemoryRecord, parse_iso, split_knowledge_human, to_iso, utcnow

INITIAL_EASE = 2.5
MIN_EASE = 1.3
MAX_EASE = 2.8
MAX_INTERVAL_DAYS = 180
REQUEUE_MINUTES = 10
MANUAL_PLAN_MINUTES = 15

RATING_LABELS = {0: "忘记", 1: "模糊", 2: "掌握", 3: "熟练"}
RATING_HINTS = {
    0: "完全想不起来",
    1: "有印象但说不清",
    2: "基本能讲明白",
    3: "能举例、能迁移",
}
STATUS_LABELS = {
    "new": "新知识",
    "learning": "学习中",
    "review": "复习中",
    "mastered": "已掌握",
}


def load_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - a missing tz database should not break the app
        return ZoneInfo("UTC")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _local_date(value: datetime, tz: ZoneInfo) -> date:
    return _as_utc(value).astimezone(tz).date()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _truncate(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class Profile:
    name: str
    goal: str
    daily_minutes: int = 20
    style: str = ""
    entry_id: str | None = None
    at: datetime | None = None

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "goal": self.goal,
            "daily_minutes": self.daily_minutes,
            "style": self.style,
            "entry_id": self.entry_id,
            "at": to_iso(self.at) if self.at else None,
        }


@dataclass
class KnowledgeItem:
    item_id: str
    entry_id: str
    topic: str
    prompt: str
    answer: str
    source_id: str | None
    created_at: datetime
    record: MemoryRecord


@dataclass
class ReviewEvent:
    event_id: str
    item_id: str
    rating: int
    note: str
    at: datetime
    session_id: str
    entry_id: str


@dataclass
class Struggle:
    struggle_id: str
    item_id: str
    text: str
    status: str
    at: datetime
    entry_id: str


@dataclass
class Session:
    session_id: str
    started_at: datetime
    ended_at: datetime
    reviewed: int
    ratings: dict[int, int]
    next_action: str
    topics: list[str]
    duration_minutes: int
    entry_id: str


@dataclass
class LearnerState:
    profile: Profile
    items: list[KnowledgeItem]
    reviews: list[ReviewEvent]
    struggles: list[Struggle]
    sessions: list[Session]
    records: list[MemoryRecord]


@dataclass
class ItemState:
    item: KnowledgeItem
    reviews: list[ReviewEvent]
    struggles: list[Struggle]
    ease: float
    interval_days: int
    lapses: int
    due_at: datetime
    mastery: int
    status: str

    @property
    def is_new(self) -> bool:
        return not self.reviews

    @property
    def last_review(self) -> ReviewEvent | None:
        return self.reviews[-1] if self.reviews else None

    @property
    def last_rating(self) -> int | None:
        return self.last_review.rating if self.last_review else None

    @property
    def open_struggles(self) -> list[Struggle]:
        return [struggle for struggle in self.struggles if struggle.status == "open"]

    def overdue_days(self, now: datetime) -> int:
        if self.is_new or self.due_at >= now:
            return 0
        return max(0, int((now - self.due_at).total_seconds() // 86_400))


# ----------------------------------------------------------------------
# Parsing memory records into state
# ----------------------------------------------------------------------


def parse_state(
    records: list[MemoryRecord],
    *,
    fallback_name: str,
    fallback_goal: str = "",
    default_minutes: int = 20,
    default_style: str = "",
) -> LearnerState:
    profile: Profile | None = None
    items: dict[str, KnowledgeItem] = {}
    reviews: list[ReviewEvent] = []
    struggles: list[Struggle] = []
    sessions: list[Session] = []

    for record in records:
        if record.state != "active":
            continue
        meta = record.meta or {}
        if record.kind == "profile":
            candidate = Profile(
                name=str(meta.get("name") or fallback_name),
                goal=str(meta.get("goal") or fallback_goal),
                daily_minutes=int(meta.get("daily_minutes") or default_minutes),
                style=str(meta.get("style") or default_style),
                entry_id=record.entry_id,
                at=record.at,
            )
            if profile is None or (candidate.at or datetime.min.replace(tzinfo=UTC)) >= (
                profile.at or datetime.min.replace(tzinfo=UTC)
            ):
                profile = candidate
        elif record.kind == "knowledge":
            item_id = str(meta.get("id") or record.entry_id)
            prompt, answer = split_knowledge_human(record.human)
            meta_prompt = meta.get("prompt")
            if isinstance(meta_prompt, str) and meta_prompt.strip():
                prompt = meta_prompt.strip()
            meta_answer = meta.get("answer")
            if isinstance(meta_answer, str) and meta_answer.strip():
                answer = meta_answer.strip()
            items[item_id] = KnowledgeItem(
                item_id=item_id,
                entry_id=record.entry_id,
                topic=str(meta.get("topic") or "未分类"),
                prompt=prompt,
                answer=answer,
                source_id=str(meta["source_id"]) if meta.get("source_id") else None,
                created_at=record.at or utcnow(),
                record=record,
            )

    for record in records:
        if record.state != "active":
            continue
        meta = record.meta or {}
        if record.kind == "review":
            item_id = str(meta.get("item_id") or "")
            when = record.at
            if item_id not in items or when is None:
                continue
            rating = int(meta.get("rating", 2))
            reviews.append(
                ReviewEvent(
                    event_id=str(meta.get("id") or record.entry_id),
                    item_id=item_id,
                    rating=max(0, min(3, rating)),
                    note=str(meta.get("note") or ""),
                    at=when,
                    session_id=str(meta.get("session_id") or ""),
                    entry_id=record.entry_id,
                )
            )
        elif record.kind == "struggle":
            item_id = str(meta.get("item_id") or "")
            when = record.at
            if item_id not in items or when is None:
                continue
            struggles.append(
                Struggle(
                    struggle_id=str(meta.get("id") or record.entry_id),
                    item_id=item_id,
                    text=str(meta.get("text") or record.human),
                    status=str(meta.get("status") or "open"),
                    at=when,
                    entry_id=record.entry_id,
                )
            )
        elif record.kind == "session":
            started = parse_iso(meta.get("started_at")) or record.at or utcnow()
            ended = parse_iso(meta.get("ended_at")) or record.at or started
            raw_ratings = meta.get("ratings") if isinstance(meta.get("ratings"), dict) else {}
            ratings = {int(key): int(value) for key, value in raw_ratings.items() if str(key).isdigit()}
            topics = meta.get("topics") if isinstance(meta.get("topics"), list) else []
            sessions.append(
                Session(
                    session_id=str(meta.get("session_id") or meta.get("id") or record.entry_id),
                    started_at=started,
                    ended_at=ended,
                    reviewed=int(meta.get("reviewed") or 0),
                    ratings=ratings,
                    next_action=str(meta.get("next_action") or ""),
                    topics=[str(topic) for topic in topics],
                    duration_minutes=int(meta.get("duration_minutes") or 0),
                    entry_id=record.entry_id,
                )
            )

    if profile is None:
        profile = Profile(
            name=fallback_name,
            goal=fallback_goal,
            daily_minutes=default_minutes,
            style=default_style,
        )

    reviews.sort(key=lambda event: event.at)
    struggles.sort(key=lambda struggle: struggle.at)
    sessions.sort(key=lambda session: session.ended_at)
    ordered_items = sorted(items.values(), key=lambda item: item.created_at)
    return LearnerState(
        profile=profile,
        items=ordered_items,
        reviews=reviews,
        struggles=struggles,
        sessions=sessions,
        records=records,
    )


# ----------------------------------------------------------------------
# Scheduling
# ----------------------------------------------------------------------


def replay_item(
    reviews: list[ReviewEvent], created_at: datetime
) -> tuple[float, int, int, datetime]:
    ease = INITIAL_EASE
    interval = 0
    lapses = 0
    due_at = created_at
    for review in sorted(reviews, key=lambda event: event.at):
        rating = review.rating
        if rating == 0:
            interval = 0
            ease = max(MIN_EASE, ease - 0.2)
            lapses += 1
            due_at = review.at + timedelta(minutes=REQUEUE_MINUTES)
        else:
            if interval == 0:
                interval = {1: 1, 2: 2, 3: 4}[rating]
            else:
                factor = {1: 1.15, 2: ease, 3: ease * 1.3}[rating]
                interval = max(1, round(interval * factor))
            interval = min(MAX_INTERVAL_DAYS, interval)
            ease = _clamp(ease + {1: -0.15, 2: 0.0, 3: 0.1}[rating], MIN_EASE, MAX_EASE)
            due_at = review.at + timedelta(days=interval)
    return ease, interval, lapses, due_at


def mastery_of(reviews: list[ReviewEvent], interval: int, lapses: int) -> int:
    if not reviews:
        return 0
    recent = reviews[-3:]
    quality = sum({0: 0.0, 1: 0.35, 2: 0.75, 3: 1.0}[review.rating] for review in recent) / len(recent)
    interval_factor = min(interval, 30) / 30
    score = quality * 55 + interval_factor * 45 - min(lapses, 4) * 4
    return int(round(_clamp(score, 0, 100)))


def status_of(reviews: list[ReviewEvent], interval: int) -> str:
    if not reviews:
        return "new"
    last = reviews[-1].rating
    if interval == 0 or last <= 1 or interval < 3:
        return "learning"
    if interval >= 21 and last >= 2:
        return "mastered"
    return "review"


def build_item_states(state: LearnerState) -> list[ItemState]:
    reviews_by_item: dict[str, list[ReviewEvent]] = {}
    for review in state.reviews:
        reviews_by_item.setdefault(review.item_id, []).append(review)
    struggles_by_item: dict[str, list[Struggle]] = {}
    for struggle in state.struggles:
        struggles_by_item.setdefault(struggle.item_id, []).append(struggle)

    result: list[ItemState] = []
    for item in state.items:
        item_reviews = reviews_by_item.get(item.item_id, [])
        item_struggles = struggles_by_item.get(item.item_id, [])
        ease, interval, lapses, due_at = replay_item(item_reviews, item.created_at)
        result.append(
            ItemState(
                item=item,
                reviews=item_reviews,
                struggles=item_struggles,
                ease=ease,
                interval_days=interval,
                lapses=lapses,
                due_at=due_at,
                mastery=mastery_of(item_reviews, interval, lapses),
                status=status_of(item_reviews, interval),
            )
        )
    return result


# ----------------------------------------------------------------------
# Public views
# ----------------------------------------------------------------------


def public_item(item_state: ItemState, now: datetime) -> dict[str, Any]:
    item = item_state.item
    last = item_state.last_review
    overdue = item_state.overdue_days(now)
    return {
        "item_id": item.item_id,
        "entry_id": item.entry_id,
        "topic": item.topic,
        "prompt": item.prompt,
        "answer": item.answer,
        "source_id": item.source_id,
        "created_at": to_iso(item.created_at),
        "status": item_state.status,
        "status_label": STATUS_LABELS[item_state.status],
        "mastery": item_state.mastery,
        "ease": round(item_state.ease, 2),
        "interval_days": item_state.interval_days,
        "lapses": item_state.lapses,
        "due_at": to_iso(item_state.due_at),
        "overdue_days": overdue,
        "is_new": item_state.is_new,
        "is_due": item_state.due_at <= now,
        "review_count": len(item_state.reviews),
        "last_reviewed_at": to_iso(last.at) if last else None,
        "last_rating": last.rating if last else None,
        "last_rating_label": RATING_LABELS[last.rating] if last else None,
        "open_struggles": [public_struggle(struggle, item) for struggle in item_state.open_struggles],
    }


def public_struggle(struggle: Struggle, item: KnowledgeItem | None = None) -> dict[str, Any]:
    return {
        "struggle_id": struggle.struggle_id,
        "item_id": struggle.item_id,
        "topic": item.topic if item else "",
        "prompt": item.prompt if item else "",
        "text": struggle.text,
        "status": struggle.status,
        "at": to_iso(struggle.at),
        "entry_id": struggle.entry_id,
    }


def public_session(session: Session) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "started_at": to_iso(session.started_at),
        "ended_at": to_iso(session.ended_at),
        "reviewed": session.reviewed,
        "ratings": {str(key): value for key, value in session.ratings.items()},
        "next_action": session.next_action,
        "topics": session.topics,
        "duration_minutes": session.duration_minutes,
        "entry_id": session.entry_id,
    }


def _reason(code: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "text": text, **extra}


def plan_reasons(item_state: ItemState, now: datetime) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    for struggle in item_state.open_struggles[:2]:
        reasons.append(
            _reason(
                "struggle",
                f"你记录过卡点：{_truncate(struggle.text, 42)}",
                at=to_iso(struggle.at),
                entry_id=struggle.entry_id,
            )
        )
    if item_state.is_new:
        reasons.append(_reason("new", "新知识，第一次学习"))
    else:
        overdue = item_state.overdue_days(now)
        if overdue >= 1:
            reasons.append(_reason("overdue", f"已逾期 {overdue} 天"))
    if item_state.lapses:
        reasons.append(_reason("lapse", f"曾遗忘 {item_state.lapses} 次"))
    last = item_state.last_review
    if last is not None:
        reasons.append(
            _reason(
                "last",
                f"上次自评：{RATING_LABELS[last.rating]}",
                at=to_iso(last.at),
                entry_id=last.entry_id,
            )
        )
    if not reasons:
        reasons.append(_reason("scheduled", f"按 {item_state.interval_days} 天间隔到期"))
    return reasons


def _priority(item_state: ItemState, now: datetime) -> tuple[Any, ...]:
    return (
        0 if item_state.open_struggles else 1,
        -item_state.overdue_days(now),
        -item_state.lapses,
        item_state.last_rating if item_state.last_rating is not None else 9,
        -item_state.mastery,
        item_state.item.created_at,
    )


def _interleave(states: list[ItemState]) -> list[ItemState]:
    """Spread topics so one subject does not monopolise the first cards."""

    buckets: dict[str, list[ItemState]] = {}
    for state in states:
        buckets.setdefault(state.item.topic, []).append(state)
    ordered: list[ItemState] = []
    while any(buckets.values()):
        for topic in list(buckets):
            if buckets[topic]:
                ordered.append(buckets[topic].pop(0))
    return ordered


def build_plan(
    state: LearnerState,
    item_states: list[ItemState],
    now: datetime,
    *,
    max_items: int | None = None,
    include_early: bool = False,
) -> dict[str, Any]:
    profile = state.profile
    budget = max(5, int(profile.daily_minutes or 20))
    capacity = max_items or max(3, min(12, round(budget / 1.8)))
    capacity = max(1, min(15, int(capacity)))

    due = [item for item in item_states if item.due_at <= now]
    due_review = sorted([item for item in due if not item.is_new], key=lambda item: _priority(item, now))
    new_items = [item for item in due if item.is_new]
    new_items.sort(key=lambda item: item.item.created_at)

    max_new = max(1, round(capacity * 0.4)) if new_items else 0
    selected: list[ItemState] = []
    if due_review and new_items:
        review_quota = max(1, capacity - min(len(new_items), max_new))
        selected.extend(due_review[:review_quota])
        selected.extend(new_items[:max_new])
        selected.extend(due_review[review_quota:])
        selected.extend(new_items[max_new:])
    else:
        selected.extend(due_review)
        selected.extend(new_items)

    if include_early and len(selected) < capacity:
        chosen = {item.item.item_id for item in selected}
        upcoming = sorted(
            [item for item in item_states if item.item.item_id not in chosen and item.due_at > now],
            key=lambda item: item.due_at,
        )
        selected.extend(upcoming[: capacity - len(selected)])

    selected = _interleave(selected[:capacity])
    estimated = math.ceil(sum(2.0 if item.is_new else 1.5 for item in selected))

    plan_items: list[dict[str, Any]] = []
    for item_state in selected:
        payload = public_item(item_state, now)
        payload["reasons"] = plan_reasons(item_state, now)
        payload["estimated_minutes"] = 2.0 if item_state.is_new else 1.5
        plan_items.append(payload)

    future_due = sorted(
        [item.due_at for item in item_states if item.due_at > now],
    )
    empty = not plan_items
    if empty:
        if not item_states:
            empty_reason = "还没有知识卡片，先导入一段笔记或添加第一张卡片。"
        elif include_early:
            empty_reason = "所有卡片都已经安排好了，休息一下吧。"
        else:
            empty_reason = "今天没有到期任务，可以点「提前复习」巩固最接近到期的一张。"
    else:
        empty_reason = None

    review_total = len(state.reviews)
    why = (
        f"从 {len(item_states)} 张知识卡和 {review_total} 条复习记忆中挑出 {len(plan_items)} 项："
        "先处理你记过的卡点与逾期项，再补新知识。"
    )
    return {
        "items": plan_items,
        "capacity": capacity,
        "budget_minutes": budget,
        "estimated_minutes": estimated,
        "include_early": include_early,
        "empty": empty,
        "empty_reason": empty_reason,
        "why": why,
        "next_due_at": to_iso(future_due[0]) if future_due else None,
    }


def build_continuity(state: LearnerState, item_states: list[ItemState], now: datetime) -> dict[str, Any]:
    latest_session = state.sessions[-1] if state.sessions else None
    latest_review = state.reviews[-1] if state.reviews else None
    open_struggles = sorted(
        [struggle for struggle in state.struggles if struggle.status == "open"],
        key=lambda struggle: struggle.at,
        reverse=True,
    )
    moment = latest_session.ended_at if latest_session else (latest_review.at if latest_review else None)
    if moment is None:
        return {
            "has_history": False,
            "headline": "第一次见面",
            "body": "我会从今天开始记住你的节奏、卡点和偏好；下次打开时，我们直接接着来。",
            "days_since_last": None,
            "last_seen_at": None,
            "last_session": None,
            "top_struggles": [],
        }
    days = max(0, (_as_utc(now) - _as_utc(moment)).days)
    if latest_session and latest_session.next_action:
        body = latest_session.next_action
    elif open_struggles:
        body = f"你上次留下的卡点是：{_truncate(open_struggles[0].text, 60)}"
    elif latest_review:
        body = f"上次复习到「{_truncate(_item_prompt(state, latest_review.item_id), 30)}」，自评{RATING_LABELS[latest_review.rating]}。"
    else:
        body = "我会继续按你的节奏安排复习。"
    if days == 0:
        headline = "今天已经学过了"
    elif days == 1:
        headline = "昨天已经学过了"
    else:
        headline = f"距上次学习 {days} 天"
    by_id = {item_state.item.item_id: item_state.item for item_state in item_states}
    return {
        "has_history": True,
        "headline": headline,
        "body": body,
        "days_since_last": days,
        "last_seen_at": to_iso(moment),
        "last_session": public_session(latest_session) if latest_session else None,
        "top_struggles": [
            public_struggle(struggle, by_id.get(struggle.item_id)) for struggle in open_struggles[:3]
        ],
    }


def _item_prompt(state: LearnerState, item_id: str) -> str:
    for item in state.items:
        if item.item_id == item_id:
            return item.prompt
    return "已归档的知识"


def build_coach_memory(state: LearnerState, item_states: list[ItemState], records: list[MemoryRecord]) -> dict[str, Any]:
    by_id = {item_state.item.item_id: item_state.item for item_state in item_states}
    open_struggles = sorted(
        [struggle for struggle in state.struggles if struggle.status == "open"],
        key=lambda struggle: struggle.at,
        reverse=True,
    )
    last_session = state.sessions[-1] if state.sessions else None
    active_kinds: dict[str, int] = {}
    for record in records:
        if record.state == "active":
            active_kinds[record.kind] = active_kinds.get(record.kind, 0) + 1
    preferences = []
    if state.profile.goal:
        preferences.append({"label": "目标", "text": state.profile.goal})
    if state.profile.daily_minutes:
        preferences.append({"label": "节奏", "text": f"每天 {state.profile.daily_minutes} 分钟"})
    if state.profile.style:
        preferences.append({"label": "偏好", "text": state.profile.style})
    return {
        "summary": (
            f"我记得你 {len(state.items)} 张卡片、{len(state.reviews)} 次复习、"
            f"{len(open_struggles)} 个未解决卡点。"
        ),
        "weak_points": [
            {
                "text": struggle.text,
                "topic": by_id[struggle.item_id].topic if struggle.item_id in by_id else "",
                "at": to_iso(struggle.at),
                "entry_id": struggle.entry_id,
                "item_id": struggle.item_id,
            }
            for struggle in open_struggles[:3]
        ],
        "preferences": preferences,
        "last_next_action": last_session.next_action if last_session else None,
        "memory_counts": active_kinds,
    }


def _streak_ending(review_dates: set[date], day: date) -> int:
    streak = 0
    cursor = day
    while cursor in review_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _streak(review_dates: set[date], today: date) -> int:
    """Days in a row up to today, tolerating a not-yet-studied today."""

    if not review_dates:
        return 0
    return max(
        _streak_ending(review_dates, today),
        _streak_ending(review_dates, today - timedelta(days=1)),
    )


def build_stats(
    state: LearnerState,
    item_states: list[ItemState],
    *,
    inventory: dict[str, Any],
    now: datetime,
    tz: ZoneInfo,
) -> dict[str, Any]:
    today = _local_date(now, tz)
    status_counts = {"new": 0, "learning": 0, "review": 0, "mastered": 0}
    for item_state in item_states:
        status_counts[item_state.status] += 1
    open_struggles = [struggle for struggle in state.struggles if struggle.status == "open"]
    review_dates = {_local_date(review.at, tz) for review in state.reviews}
    reviews_7d = [review for review in state.reviews if _as_utc(review.at) >= _as_utc(now) - timedelta(days=7)]
    activity = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        count = sum(1 for review in state.reviews if _local_date(review.at, tz) == day)
        activity.append({"date": day.isoformat(), "label": day.strftime("%m/%d"), "count": count})
    reviewed_items = [item for item in item_states if item.reviews]
    average_mastery = (
        round(sum(item.mastery for item in reviewed_items) / len(reviewed_items)) if reviewed_items else 0
    )
    topic_map: dict[str, dict[str, Any]] = {}
    for item_state in item_states:
        entry = topic_map.setdefault(
            item_state.item.topic,
            {"topic": item_state.item.topic, "items": 0, "mastery_sum": 0, "reviewed": 0, "due": 0, "struggles": 0},
        )
        entry["items"] += 1
        entry["mastery_sum"] += item_state.mastery
        entry["reviewed"] += 1 if item_state.reviews else 0
        entry["due"] += 1 if item_state.due_at <= now else 0
        entry["struggles"] += len(item_state.open_struggles)
    topics = []
    for entry in topic_map.values():
        topics.append(
            {
                "topic": entry["topic"],
                "items": entry["items"],
                "reviewed": entry["reviewed"],
                "due": entry["due"],
                "struggles": entry["struggles"],
                "mastery": round(entry["mastery_sum"] / entry["items"]) if entry["items"] else 0,
            }
        )
    topics.sort(key=lambda item: (-item["items"], item["topic"]))
    sessions_total = len(state.sessions)
    return {
        "items_total": len(item_states),
        "status_counts": status_counts,
        "due_now": sum(1 for item in item_states if item.due_at <= now),
        "due_review": sum(1 for item in item_states if item.due_at <= now and not item.is_new),
        "new_items": status_counts["new"],
        "open_struggles": len(open_struggles),
        "reviews_total": len(state.reviews),
        "reviews_7d": len(reviews_7d),
        "sessions_total": sessions_total,
        "active_days": len(review_dates),
        "streak": _streak(review_dates, today),
        "streak_current": _streak(review_dates, today),
        "streak_recent": _streak_ending(review_dates, max(review_dates)) if review_dates else 0,
        "average_mastery": average_mastery,
        "topics": topics,
        "activity_7d": activity,
        "estimated_prep_minutes_saved": sessions_total * MANUAL_PLAN_MINUTES,
        "estimated_prep_minutes_baseline": MANUAL_PLAN_MINUTES,
        "actual_review_minutes": sum(session.duration_minutes for session in state.sessions),
        "memory": {
            "revision": None,
            "records": len(state.records),
            "active": sum(1 for record in state.records if record.state == "active"),
            "inactive": sum(1 for record in state.records if record.state == "inactive"),
            **inventory,
        },
    }


def build_recent(state: LearnerState, records: list[MemoryRecord], limit: int = 12) -> list[dict[str, Any]]:
    events = []
    for record in records:
        if record.at is None:
            continue
        events.append(
            {
                "kind": record.kind,
                "kind_label": record.kind_label,
                "human": record.human,
                "at": to_iso(record.at),
                "entry_id": record.entry_id,
                "state": record.state,
            }
        )
    events.sort(key=lambda event: event["at"], reverse=True)
    return events[:limit]


def find_next_action(state: LearnerState, item_states: list[ItemState], now: datetime) -> str:
    with_struggle = [item for item in item_states if item.open_struggles]
    if with_struggle:
        item = sorted(with_struggle, key=lambda state: state.open_struggles[-1].at, reverse=True)[0]
        return f"先攻「{_truncate(item.item.prompt, 34)}」：你记录过「{_truncate(item.open_struggles[-1].text, 40)}」"
    overdue = [item for item in item_states if item.due_at <= now and not item.is_new]
    if overdue:
        item = sorted(overdue, key=lambda state: state.due_at)[0]
        return f"先复习「{_truncate(item.item.prompt, 34)}」（已逾期 {item.overdue_days(now)} 天）"
    upcoming = sorted([item for item in item_states if item.due_at > now], key=lambda state: state.due_at)
    if upcoming:
        item = upcoming[0]
        return f"下一次复习「{_truncate(item.item.prompt, 34)}」，{to_iso(item.due_at)[:10]} 到期"
    if item_states:
        return "今天的任务已经完成，休息一下，明天继续。"
    return "先导入一段笔记或添加第一张知识卡，我会安排第一次复习。"


def build_learner_view(
    state: LearnerState,
    *,
    inventory: dict[str, Any],
    memory_revision: int,
    now: datetime,
    tz: ZoneInfo,
    include_early: bool = False,
    max_items: int | None = None,
) -> dict[str, Any]:
    item_states = build_item_states(state)
    plan = build_plan(state, item_states, now, max_items=max_items, include_early=include_early)
    continuity = build_continuity(state, item_states, now)
    coach_memory = build_coach_memory(state, item_states, state.records)
    stats = build_stats(state, item_states, inventory=inventory, now=now, tz=tz)
    stats["memory"]["revision"] = memory_revision
    return {
        "profile": state.profile.public(),
        "items": [public_item(item_state, now) for item_state in item_states],
        "plan": plan,
        "continuity": continuity,
        "coach_memory": coach_memory,
        "stats": stats,
        "topics": stats["topics"],
        "recent": build_recent(state, state.records),
        "struggles": [
            public_struggle(struggle, _item_by_id(state, struggle.item_id))
            for struggle in sorted(state.struggles, key=lambda struggle: struggle.at, reverse=True)
        ],
        "sessions": [public_session(session) for session in reversed(state.sessions)],
        "reviews": [
            {
                "event_id": review.event_id,
                "item_id": review.item_id,
                "prompt": _item_prompt(state, review.item_id),
                "rating": review.rating,
                "rating_label": RATING_LABELS[review.rating],
                "note": review.note,
                "at": to_iso(review.at),
                "session_id": review.session_id,
                "entry_id": review.entry_id,
            }
            for review in reversed(state.reviews)
        ],
        "memory": stats["memory"],
        "next_action": find_next_action(state, item_states, now),
    }


def _item_by_id(state: LearnerState, item_id: str) -> KnowledgeItem | None:
    for item in state.items:
        if item.item_id == item_id:
            return item
    return None
