from __future__ import annotations

from app.importer import MAX_ITEMS_PER_IMPORT, parse_notes

HEADING_NOTES = """# 机器学习

## 梯度下降
损失函数在当前点的梯度指向增长最快的方向，负梯度就是下降最快的方向，参数沿负梯度更新。

## 偏差与方差
高偏差是模型太简单，训练集和验证集都差，属于欠拟合；高方差是对训练集过拟合。
"""

QA_NOTES = """Q: 什么是梯度下降？
A: 沿着负梯度方向更新参数，让损失函数尽快下降。

Q: 学习率是什么？
A: 控制每一步更新步长的超参数，太大会震荡，太小会收敛慢。
"""


def test_markdown_headings_become_cards():
    parsed = parse_notes(HEADING_NOTES, "")
    assert parsed.title == "机器学习"
    assert parsed.topic == "机器学习"
    assert [item.prompt for item in parsed.items] == ["梯度下降", "偏差与方差"]
    assert all(item.topic == "机器学习" for item in parsed.items)
    assert "负梯度" in parsed.items[0].answer


def test_default_topic_overrides_document_topic():
    parsed = parse_notes(HEADING_NOTES, "算法")
    assert parsed.topic == "机器学习"
    assert all(item.topic == "算法" for item in parsed.items)


def test_qa_blocks_become_cards():
    parsed = parse_notes(QA_NOTES, "机器学习")
    assert len(parsed.items) == 2
    assert parsed.items[0].prompt == "什么是梯度下降？"
    assert "负梯度方向" in parsed.items[0].answer
    assert parsed.items[1].prompt == "学习率是什么？"


def test_plain_paragraphs_become_cards():
    text = (
        "梯度下降沿着负梯度方向更新参数。学习率决定每一步的步长，太大会震荡。\n\n"
        "正则化通过惩罚模型复杂度来缓解过拟合。L2 正则让权重尽量小。"
    )
    parsed = parse_notes(text, "机器学习")
    assert len(parsed.items) == 2
    assert parsed.items[0].prompt == "梯度下降沿着负梯度方向更新参数"
    assert parsed.items[0].answer.startswith("梯度下降沿着负梯度方向")


def test_duplicate_prompts_are_deduped():
    text = """## 梯度下降
第一段说明，梯度下降沿负梯度方向更新参数，是最常用的优化方法之一。

## 梯度下降
第二段说明，内容不同但标题重复，因此只保留第一张卡片。
"""
    parsed = parse_notes(text, "机器学习")
    assert len(parsed.items) == 1
    assert "第一段" in parsed.items[0].answer


def test_short_input_reports_warning():
    parsed = parse_notes("太短了", "机器学习")
    assert parsed.items == []
    assert parsed.warnings


def test_import_is_capped():
    blocks = [
        f"## 概念 {index}\n这是第 {index} 个概念的说明，长度足够被识别为一张知识卡片。" for index in range(120)
    ]
    parsed = parse_notes("\n\n".join(blocks), "机器学习")
    assert len(parsed.items) == MAX_ITEMS_PER_IMPORT


def test_answers_are_clipped_to_budget():
    parsed = parse_notes("## 大段说明\n" + "学习" * 4000, "机器学习", max_answer_bytes=200)
    assert len(parsed.items) == 1
    assert parsed.items[0].answer.endswith("…")
    assert len(parsed.items[0].answer.encode("utf-8")) <= 200
