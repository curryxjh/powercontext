from __future__ import annotations

from datetime import timedelta

from app.coach import (
    MAX_INTERVAL_DAYS,
    REQUEUE_MINUTES,
    ReviewEvent,
    build_continuity,
    build_item_states,
    build_plan,
    build_stats,
    find_next_action,
    load_timezone,
    mastery_of,
    parse_state,
    replay_item,
    status_of,
)
from app.records import MemoryRecord, knowledge_human, to_iso, utcnow

NOW = utcnow()


def rec(kind: str, human: str, meta: dict, *, state: str = "active") -> MemoryRecord:
    return MemoryRecord(
        entry_id=f"mem_ent_{meta.get('id', kind)}",
        version_id="ver_1",
        kind=kind,
        state=state,
        human=human,
        meta=meta,
        text=human,
        memory_revision=1,
        citation=None,
    )


def knowledge(item_id: str, topic: str, prompt: str, at, *, state: str = "active") -> MemoryRecord:
    answer = prompt + "的说明"
    return rec(
        "knowledge",
        knowledge_human(topic, prompt, answer),
        {"id": item_id, "topic": topic, "prompt": prompt, "answer": answer, "at": to_iso(at)},
        state=state,
    )


def review(item_id: str, rating: int, at, review_id: str, session_id: str = "s_1") -> MemoryRecord:
    return rec(
        "review",
        f"复习，自评 {rating}",
        {
            "id": review_id,
            "item_id": item_id,
            "rating": rating,
            "session_id": session_id,
            "at": to_iso(at),
        },
    )


def event(rating: int, at, item_id: str = "k1") -> ReviewEvent:
    return ReviewEvent(
        event_id=f"r_{rating}_{at.timestamp()}",
        item_id=item_id,
        rating=rating,
        note="",
        at=at,
        session_id="s_1",
        entry_id=f"mem_ent_r_{at.timestamp()}",
    )


# ----------------------------------------------------------------------
# Scheduling
# ----------------------------------------------------------------------


def test_replay_new_item_is_due_at_creation():
    ease, interval, lapses, due_at = replay_item([], NOW)
    assert ease == 2.5
    assert interval == 0
    assert lapses == 0
    assert due_at == NOW


def test_replay_good_rating_sets_first_interval():
    ease, interval, lapses, due_at = replay_item([event(2, NOW)], NOW)
    assert interval == 2
    assert ease == 2.5
    assert lapses == 0
    assert due_at == NOW + timedelta(days=2)


def test_replay_forgot_requeues_soon_and_counts_lapse():
    ease, interval, lapses, due_at = replay_item([event(0, NOW)], NOW)
    assert interval == 0
    assert lapses == 1
    assert ease == 2.3
    assert due_at == NOW + timedelta(minutes=REQUEUE_MINUTES)


def test_replay_multiple_good_reviews_grow_interval():
    sequence = [event(3, NOW), event(3, NOW + timedelta(days=4))]
    ease, interval, lapses, due_at = replay_item(sequence, NOW)
    assert interval == 14
    assert ease == 2.7
    assert lapses == 0
    assert due_at == sequence[-1].at + timedelta(days=14)


def test_replay_interval_is_capped():
    reviews = [event(3, NOW + timedelta(days=index)) for index in range(40)]
    _, interval, _, _ = replay_item(reviews, NOW)
    assert interval == MAX_INTERVAL_DAYS


def test_status_transitions():
    assert status_of([], 0) == "new"
    assert status_of([event(1, NOW)], 1) == "learning"
    assert status_of([event(0, NOW)], 0) == "learning"
    assert status_of([event(2, NOW)], 2) == "learning"
    assert status_of([event(2, NOW)], 3) == "review"
    assert status_of([event(2, NOW)], 21) == "mastered"


def test_mastery_bounds():
    assert mastery_of([], 0, 0) == 0
    assert mastery_of([event(3, NOW)], 30, 0) == 100
    assert mastery_of([event(0, NOW)], 0, 1) == 0
    assert 0 < mastery_of([event(2, NOW)], 2, 0) < 100


# ----------------------------------------------------------------------
# Parsing memory into learner state
# ----------------------------------------------------------------------


def test_parse_state_picks_latest_profile_and_active_records():
    older = rec(
        "profile",
        "我是旧名字",
        {"name": "旧名字", "goal": "旧目标", "daily_minutes": 10, "at": to_iso(NOW - timedelta(days=5))},
    )
    newer = rec(
        "profile",
        "我是新名字",
        {"name": "新名字", "goal": "新目标", "daily_minutes": 30, "at": to_iso(NOW)},
    )
    retired = knowledge("k_old", "线代", "旧的卡片", NOW - timedelta(days=2), state="inactive")
    state = parse_state(
        [older, newer, retired, knowledge("k1", "线代", "特征值", NOW - timedelta(days=1))],
        fallback_name="测试",
    )
    assert state.profile.name == "新名字"
    assert state.profile.daily_minutes == 30
    assert [item.item_id for item in state.items] == ["k1"]


def test_parse_state_joins_reviews_and_struggles_to_items():
    records = [
        knowledge("k1", "概率", "贝叶斯公式", NOW - timedelta(days=3)),
        review("k1", 1, NOW - timedelta(days=2), "r1"),
        rec(
            "struggle",
            "卡点：分不清先验和后验",
            {"id": "st1", "item_id": "k1", "text": "分不清先验和后验", "status": "open", "at": to_iso(NOW)},
        ),
        rec(
            "session",
            "本次复习 1 项",
            {
                "id": "se1",
                "session_id": "s_1",
                "started_at": to_iso(NOW - timedelta(minutes=20)),
                "ended_at": to_iso(NOW),
                "reviewed": 1,
                "next_action": "先攻贝叶斯公式",
                "at": to_iso(NOW),
            },
        ),
    ]
    state = parse_state(records, fallback_name="测试")
    item_state = build_item_states(state)[0]
    assert item_state.reviews[0].rating == 1
    assert item_state.open_struggles[0].text == "分不清先验和后验"
    assert state.sessions[0].next_action == "先攻贝叶斯公式"


# ----------------------------------------------------------------------
# Planning and continuity
# ----------------------------------------------------------------------


def test_plan_prioritises_overdue_and_explains_new_cards():
    records = [
        knowledge("k1", "线代", "特征值", NOW - timedelta(days=5)),
        review("k1", 1, NOW - timedelta(days=4), "r1"),
        knowledge("k2", "概率", "贝叶斯公式", NOW - timedelta(days=1)),
    ]
    state = parse_state(records, fallback_name="测试")
    plan = build_plan(state, build_item_states(state), NOW)
    assert plan["empty"] is False
    codes = {item["item_id"]: [reason["code"] for reason in item["reasons"]] for item in plan["items"]}
    assert "overdue" in codes["k1"]
    assert codes["k2"] == ["new"]
    assert plan["estimated_minutes"] >= len(plan["items"])


def test_plan_skips_future_cards_unless_early_review_requested():
    records = [
        knowledge("k1", "线代", "特征值", NOW - timedelta(days=5)),
        review("k1", 3, NOW - timedelta(days=3), "r1"),
    ]
    state = parse_state(records, fallback_name="测试")
    states = build_item_states(state)
    regular = build_plan(state, states, NOW)
    early = build_plan(state, states, NOW, include_early=True)
    assert regular["empty"] is True
    assert regular["empty_reason"]
    assert early["empty"] is False
    assert early["items"][0]["item_id"] == "k1"


def test_plan_without_cards_explains_first_step():
    state = parse_state([], fallback_name="测试")
    plan = build_plan(state, [], NOW)
    assert plan["empty"] is True
    assert "导入" in plan["empty_reason"]


def test_continuity_uses_latest_session():
    records = [
        knowledge("k1", "概率", "贝叶斯公式", NOW - timedelta(days=3)),
        rec(
            "session",
            "本次复习 1 项",
            {
                "id": "se1",
                "session_id": "s_1",
                "started_at": to_iso(NOW - timedelta(minutes=30)),
                "ended_at": to_iso(NOW - timedelta(minutes=15)),
                "reviewed": 1,
                "next_action": "先攻贝叶斯公式",
                "at": to_iso(NOW - timedelta(minutes=15)),
            },
        ),
    ]
    state = parse_state(records, fallback_name="测试")
    continuity = build_continuity(state, build_item_states(state), NOW)
    assert continuity["has_history"] is True
    assert continuity["headline"] == "今天已经学过了"
    assert continuity["body"] == "先攻贝叶斯公式"


def test_continuity_says_yesterday_when_last_session_was_yesterday():
    records = [
        knowledge("k1", "概率", "贝叶斯公式", NOW - timedelta(days=3)),
        rec(
            "session",
            "本次复习 1 项",
            {
                "id": "se1",
                "session_id": "s_1",
                "started_at": to_iso(NOW - timedelta(days=1, minutes=30)),
                "ended_at": to_iso(NOW - timedelta(days=1, minutes=15)),
                "reviewed": 1,
                "next_action": "先攻贝叶斯公式",
                "at": to_iso(NOW - timedelta(days=1, minutes=15)),
            },
        ),
    ]
    state = parse_state(records, fallback_name="测试")
    continuity = build_continuity(state, build_item_states(state), NOW)
    assert continuity["headline"] == "昨天已经学过了"
    assert continuity["days_since_last"] == 1


def test_continuity_first_meeting():
    state = parse_state([], fallback_name="测试")
    continuity = build_continuity(state, [], NOW)
    assert continuity["has_history"] is False
    assert continuity["headline"] == "第一次见面"


def test_next_action_prefers_open_struggles():
    records = [
        knowledge("k1", "概率", "贝叶斯公式", NOW - timedelta(days=5)),
        review("k1", 1, NOW - timedelta(days=4), "r1"),
        rec(
            "struggle",
            "卡点：分不清先验和后验",
            {"id": "st1", "item_id": "k1", "text": "分不清先验和后验", "status": "open", "at": to_iso(NOW)},
        ),
    ]
    state = parse_state(records, fallback_name="测试")
    action = find_next_action(state, build_item_states(state), NOW)
    assert "先攻" in action
    assert "分不清先验和后验" in action


# ----------------------------------------------------------------------
# Stats and streaks
# ----------------------------------------------------------------------


def test_streak_counts_consecutive_days_ending_today():
    today = NOW
    records = [knowledge("k1", "线代", "特征值", NOW - timedelta(days=5))]
    for offset in range(3):
        records.append(review("k1", 2, today - timedelta(days=offset), f"r{offset}"))
    state = parse_state(records, fallback_name="测试")
    stats = build_stats(
        state,
        build_item_states(state),
        inventory={},
        now=NOW,
        tz=load_timezone("UTC"),
    )
    assert stats["streak"] == 3
    assert stats["streak_current"] == 3
    assert stats["reviews_total"] == 3
    assert stats["reviews_7d"] == 3
    assert sum(day["count"] for day in stats["activity_7d"]) == 3


def test_streak_tolerates_today_not_studied_yet():
    records = [knowledge("k1", "线代", "特征值", NOW - timedelta(days=5))]
    for offset in (1, 2):
        records.append(review("k1", 2, NOW - timedelta(days=offset), f"r{offset}"))
    state = parse_state(records, fallback_name="测试")
    stats = build_stats(
        state,
        build_item_states(state),
        inventory={},
        now=NOW,
        tz=load_timezone("UTC"),
    )
    assert stats["streak"] == 2
    assert stats["streak_recent"] == 2
