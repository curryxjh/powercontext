"""Deterministic demo learner used by the one-click experience.

The data is written through the same PowerContext memory path as real usage:
sources first, then knowledge cards, then historical review events, struggle
notes and session summaries. Nothing is mocked in a side database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .memory_store import MemoryStore
from .records import knowledge_human, to_iso, utcnow
from .service import add_feedback, learner_data

DEMO_NAME = "林知夏"
DEMO_GOAL = "两周后通过机器学习期中考试，重点补概率和线代"
DEMO_MINUTES = 20
DEMO_STYLE = "图示 + 生活类比"


async def seed_demo(
    store: MemoryStore,
    settings: Settings,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = now or utcnow()
    slug = settings.demo_slug
    existing = await store.find_scope(slug)
    if existing is not None:
        records, _ = await store.list_records(existing.scope_id)
        has_cards = any(record.kind == "knowledge" and record.state == "active" for record in records)
        if has_cards and not force:
            data = await learner_data(store, settings, slug, now=moment)
            return {
                "created": False,
                "slug": slug,
                "name": data["view"]["profile"]["name"],
                "stats": data["view"]["stats"],
            }
        if force:
            await store.retire_all(existing.scope_id, reason="demo data reset")

    scope = await store.ensure_learner_scope(slug, DEMO_NAME, DEMO_GOAL)

    def ago(days: float, hours: float = 0) -> str:
        return to_iso(moment - timedelta(days=days, hours=hours))

    await store.write_profile(
        scope.scope_id,
        name=DEMO_NAME,
        goal=DEMO_GOAL,
        daily_minutes=DEMO_MINUTES,
        style=DEMO_STYLE,
        at=moment - timedelta(days=15),
    )

    # Two captured Sources back the cards, exactly as a real import would.
    note_ml = await store.capture_source(
        scope.scope_id,
        content=(
            "# 机器学习期中复习笔记\n\n"
            "## 梯度下降\n损失函数在当前点的梯度指向增长最快的方向，负梯度就是下降最快的方向。"
            "参数更新 θ ← θ - η∇L(θ)，η 是学习率，决定每步步长。\n\n"
            "## 偏差与方差\n高偏差是模型太简单，训练集和验证集都差（欠拟合）；"
            "高方差是模型对训练数据太敏感，训练集好但验证集差（过拟合）。\n\n"
            "## 交叉验证\n把数据分成 k 份轮流做验证，每个样本都参与训练和验证，降低单次划分的偶然性。\n\n"
            "## 过拟合与正则化\nL2 在损失中加入参数平方和，抑制参数过大，让模型更平滑；λ 越大正则越强，但过大导致欠拟合。\n\n"
            "## 学习率调度\n前期大步长快速下降，后期小步长在最优解附近精细收敛，减少震荡。"
            "常见策略有阶梯衰减、余弦退火。\n\n"
            "## 混淆矩阵\nprecision 问“预测为正的样本里有多少真的是正”；"
            "recall 问“真正的正样本里有多少被找出来”。\n"
        ),
        metadata={"title": "机器学习期中复习笔记.md", "kind": "seed", "topic": "机器学习基础"},
    )
    note_math = await store.capture_source(
        scope.scope_id,
        content=(
            "# 概率与线代错题本\n\n"
            "## 贝叶斯公式\nP(A|B) = P(B|A)P(A)/P(B)。先验 P(A) 结合似然 P(B|A)，"
            "再用证据 P(B) 归一化，得到后验 P(A|B)。\n\n"
            "## 最大似然估计\n选择让已观测数据出现概率最大的参数值；通常对似然函数取对数后求导，令导数为 0。\n\n"
            "## 特征值与特征向量\nAv = λv：矩阵作用在特征向量上只做缩放，不改变方向；λ 是缩放倍数。\n\n"
            "## 矩阵秩\n秩等于线性无关的行/列数。满秩方阵可逆、方程组有唯一解；"
            "秩小于未知数个数时出现自由变量，解不唯一。\n"
        ),
        metadata={"title": "概率与线代错题本.md", "kind": "seed", "topic": "概率统计"},
    )

    cards = [
        (
            "k_seed_gd",
            "机器学习基础",
            "为什么梯度下降要沿负梯度方向更新参数？",
            "损失函数在当前点的梯度指向增长最快的方向，负梯度就是下降最快的方向。"
            "参数更新 θ ← θ - η∇L(θ)，η 是学习率，决定每步步长。",
            note_ml["source_id"],
            14,
        ),
        (
            "k_seed_bv",
            "机器学习基础",
            "高偏差和高方差分别对应什么表现？",
            "高偏差是模型太简单，训练集和验证集都差（欠拟合）；高方差是模型对训练数据太敏感，"
            "训练集好但验证集差（过拟合）。",
            note_ml["source_id"],
            13,
        ),
        (
            "k_seed_cv",
            "机器学习基础",
            "k 折交叉验证为什么比单次划分更可靠？",
            "它把数据分成 k 份轮流做验证，每个样本都参与训练和验证，降低单次划分带来的偶然性，评估更稳定。",
            note_ml["source_id"],
            12,
        ),
        (
            "k_seed_bayes",
            "概率统计",
            "贝叶斯公式如何把先验和似然变成后验？",
            "P(A|B) = P(B|A)P(A)/P(B)。先验 P(A) 结合似然 P(B|A)，再用证据 P(B) 归一化，得到后验 P(A|B)。",
            note_math["source_id"],
            11,
        ),
        (
            "k_seed_mle",
            "概率统计",
            "最大似然估计在最大化什么？",
            "选择让已观测数据出现概率最大的参数值；通常对似然函数取对数后求导，令导数为 0。",
            note_math["source_id"],
            10,
        ),
        (
            "k_seed_eig",
            "线性代数",
            "特征值和特征向量描述矩阵的什么性质？",
            "Av = λv：矩阵作用在特征向量上只做缩放，不改变方向；λ 是缩放倍数，刻画矩阵在该方向上的伸缩。",
            note_math["source_id"],
            9,
        ),
        (
            "k_seed_rank",
            "线性代数",
            "矩阵的秩和方程组的解有什么关系？",
            "秩等于线性无关的行/列数。满秩方阵可逆、方程组有唯一解；"
            "秩小于未知数个数时出现自由变量，解不唯一。",
            note_math["source_id"],
            8,
        ),
        (
            "k_seed_lr",
            "机器学习基础",
            "为什么训练后期要衰减学习率？",
            "前期大步长快速下降，后期小步长在最优解附近精细收敛，减少震荡。常见策略有阶梯衰减、余弦退火。",
            note_ml["source_id"],
            14,
        ),
        (
            "k_seed_reg",
            "机器学习基础",
            "L2 正则化为什么能缓解过拟合？",
            "L2 在损失中加入参数平方和，抑制参数过大，让模型更平滑；λ 越大正则越强，但过大导致欠拟合。",
            note_ml["source_id"],
            13,
        ),
        (
            "k_seed_cm",
            "机器学习基础",
            "混淆矩阵中的 precision 和 recall 分别在问什么？",
            "precision 问“预测为正的样本里有多少真的是正”；recall 问“真正的正样本里有多少被找出来”。"
            "两者关注点不同，需要按业务取舍。",
            note_ml["source_id"],
            7,
        ),
    ]

    source_titles = {
        note_ml["source_id"]: "机器学习期中复习笔记.md",
        note_math["source_id"]: "概率与线代错题本.md",
    }
    knowledge_entries = [
        (
            "knowledge",
            knowledge_human(topic, prompt, answer),
            {
                "id": item_id,
                "topic": topic,
                "prompt": prompt,
                "source_id": source_id,
                "source_title": source_titles[source_id],
                "at": ago(days),
                "seed": True,
            },
        )
        for item_id, topic, prompt, answer, source_id, days in cards
    ]
    await store.append_many(scope.scope_id, knowledge_entries)

    reviews = [
        ("k_seed_gd", 1, 9, "", "seed-s1"),
        ("k_seed_lr", 2, 11, "", "seed-s1"),
        ("k_seed_gd", 0, 6, "把学习率和步长当成两件事，说不清 η 到底控制什么。", "seed-s2"),
        ("k_seed_bv", 0, 8, "总把偏差和方差的方向记反。", "seed-s2"),
        ("k_seed_bayes", 2, 6, "", "seed-s2"),
        ("k_seed_cv", 3, 7, "", "seed-s3"),
        ("k_seed_rank", 2, 7, "", "seed-s3"),
        ("k_seed_lr", 2, 9, "", "seed-s3"),
        ("k_seed_gd", 2, 3, "现在能说出学习率是系数、步长是结果。", "seed-s3"),
        ("k_seed_bv", 1, 5, "还是容易混，需要具体例子。", "seed-s3"),
        ("k_seed_lr", 3, 6, "", "seed-s4"),
        ("k_seed_rank", 3, 4, "", "seed-s4"),
        ("k_seed_reg", 2, 10, "", "seed-s3"),
        ("k_seed_reg", 2, 1, "", "seed-s4"),
        ("k_seed_cm", 1, 2, "precision 和 recall 的定义一紧张就混。", "seed-s4"),
        ("k_seed_lr", 3, 3, "", "seed-s4"),
    ]
    review_entries = []
    for item_id, rating, days, note, session_id in reviews:
        label = {0: "忘记", 1: "模糊", 2: "掌握", 3: "熟练"}[rating]
        prompt = next(card[2] for card in cards if card[0] == item_id)
        human = f"复习「{prompt}」，自评{label}。"
        if note:
            human += f"卡点：{note}"
        review_entries.append(
            (
                "review",
                human,
                {
                    "id": f"r_seed_{uuid.uuid4().hex[:8]}",
                    "item_id": item_id,
                    "rating": rating,
                    "note": note,
                    "at": ago(days, hours=1),
                    "session_id": session_id,
                    "seed": True,
                },
            )
        )
    await store.append_many(scope.scope_id, review_entries)

    struggle_entries = [
        (
            "struggle",
            "卡点：把学习率和步长当成两件事，说不清 η 到底控制什么。\n来自「梯度下降」的复习。",
            {
                "id": "st_seed_lr_confusion",
                "item_id": "k_seed_gd",
                "text": "把学习率和步长当成两件事，说不清 η 到底控制什么。",
                "status": "open",
                "at": ago(6, hours=1),
                "seed": True,
            },
        ),
        (
            "struggle",
            "卡点：总把偏差和方差的方向记反，需要具体例子。\n来自「偏差与方差」的复习。",
            {
                "id": "st_seed_bv_confusion",
                "item_id": "k_seed_bv",
                "text": "总把偏差和方差的方向记反，需要具体例子。",
                "status": "open",
                "at": ago(5, hours=1),
                "seed": True,
            },
        ),
        (
            "struggle",
            "卡点：分不清阶梯衰减和余弦退火。\n来自「学习率调度」的复习。（已解决）",
            {
                "id": "st_seed_schedule",
                "item_id": "k_seed_lr",
                "text": "分不清阶梯衰减和余弦退火。",
                "status": "resolved",
                "at": ago(12),
                "resolved_at": ago(9),
                "seed": True,
            },
        ),
    ]
    await store.append_many(scope.scope_id, struggle_entries)

    sessions = [
        (
            "seed-s1",
            9,
            8,
            {"1": 1, "2": 1},
            ["机器学习基础"],
            "先补「偏差与方差」的例子，再复习梯度下降。",
        ),
        (
            "seed-s2",
            6,
            10,
            {"0": 2, "2": 1},
            ["机器学习基础", "概率统计"],
            "先攻「梯度下降」：你记录过「把学习率和步长当成两件事」。",
        ),
        (
            "seed-s3",
            3,
            9,
            {"1": 1, "2": 3},
            ["机器学习基础", "线性代数"],
            "先攻「偏差与方差」：你记录过「总把偏差和方差的方向记反，需要具体例子」。",
        ),
        (
            "seed-s4",
            1,
            7,
            {"1": 1, "2": 1},
            ["机器学习基础"],
            "先攻「偏差与方差」：你记录过「总把偏差和方差的方向记反，需要具体例子」。",
        ),
    ]
    session_entries = []
    for session_id, days, minutes, ratings, topics, next_action in sessions:
        parts = " / ".join(
            f"{ {0: '忘记', 1: '模糊', 2: '掌握', 3: '熟练'}[int(key)] } {value}"
            for key, value in sorted(ratings.items())
        )
        reviewed = sum(ratings.values())
        human = (
            f"本次复习 {reviewed} 项（{parts}），涉及{'、'.join(topics)}。"
            f"下次先攻：{next_action.rstrip('。')}。"
        )
        session_entries.append(
            (
                "session",
                human,
                {
                    "id": f"se_seed_{session_id}",
                    "session_id": session_id,
                    "started_at": ago(days, hours=1),
                    "ended_at": ago(days, hours=0.5),
                    "reviewed": reviewed,
                    "ratings": ratings,
                    "topics": topics,
                    "next_action": next_action,
                    "duration_minutes": minutes,
                    "at": ago(days, hours=0.5),
                    "seed": True,
                },
            )
        )
    await store.append_many(scope.scope_id, session_entries)

    # A clearly-labelled demo feedback row, so the feedback inbox is not empty.
    await add_feedback(
        store,
        rating=4,
        text="（演示数据）希望之后能把卡点直接导出成复习清单。",
        role="演示用户",
        name="演示同学",
        now=moment - timedelta(days=5),
    )

    data = await learner_data(store, settings, slug, now=moment)
    return {
        "created": True,
        "slug": slug,
        "name": DEMO_NAME,
        "stats": data["view"]["stats"],
        "plan_items": len(data["view"]["plan"]["items"]),
        "sources": 2,
        "cards": len(cards),
        "reviews": len(reviews),
        "sessions": len(sessions),
    }
