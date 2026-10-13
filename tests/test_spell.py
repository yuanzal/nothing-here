from __future__ import annotations

import random
import unittest
from dataclasses import replace

from nothing_here.domain.daily import DailyPlan, grade
from nothing_here.domain.spell import (
    MISS_LIMIT,
    SpellMode,
    accept_invite,
    advance_spelling,
    after_plan_change,
    answers_match,
    assemble_answer,
    cells_for,
    decline_invite,
    empty_spell,
    end_spelling,
    ensure_spell_day,
    invite_threshold,
    is_mastered,
    mute_invite,
    register_miss,
    start_from_tray,
)

DAY = "2026-10-13"
CATALOG = ["apple", "book", "cat", "dog", "theme", "extra"]
FOUR = ["apple", "book", "cat", "dog"]
# 名单词全部 >80%；theme 达标可作熟词；extra 未达标
MASTERED = {
    "apple": (9, 10),
    "book": (9, 10),
    "cat": (9, 10),
    "dog": (9, 10),
    "theme": (9, 10),
    "extra": (1, 10),
}


def sealed(**kwargs: object) -> DailyPlan:
    values = dict(
        goal=4,
        day=DAY,
        collected=tuple(FOUR),
        queue=tuple(FOUR),
        phase=0,
        current="apple",
    )
    values.update(kwargs)
    return DailyPlan(**values)  # type: ignore[arg-type]


class SpellTests(unittest.TestCase):
    def test_mastery_is_strictly_above_eighty(self) -> None:
        self.assertFalse(is_mastered(0, 0))
        self.assertFalse(is_mastered(8, 10))
        self.assertTrue(is_mastered(9, 10))

    def test_unsealed_or_weak_list_does_not_invite(self) -> None:
        open_plan = DailyPlan(4, DAY, ("apple",), (), 0, "apple")
        self.assertFalse(invite_threshold(open_plan, MASTERED))
        weak = sealed()
        progress = {**MASTERED, "dog": (1, 10)}
        self.assertFalse(invite_threshold(weak, progress))

    def test_after_grade_inserts_invite_when_ready(self) -> None:
        plan = sealed(phase=2, current="theme", queue=("cat", "dog", "apple", "book"))
        spell = empty_spell(plan)
        after = grade(plan, True, CATALOG, MASTERED, random.Random(0))
        next_spell = after_plan_change(spell, plan, after, MASTERED)
        self.assertEqual(next_spell.mode, SpellMode.INVITE)
        self.assertTrue(next_spell.tray_unlocked)
        self.assertEqual(next_spell.plan.current, after.current)

    def test_decline_needs_two_cycles_before_invite_again(self) -> None:
        plan = sealed()
        spell = replace(empty_spell(plan), mode=SpellMode.INVITE, tray_unlocked=True)
        spell = decline_invite(spell)
        self.assertEqual(spell.mode, SpellMode.NORMAL)
        self.assertEqual(spell.cooldown, 2)

        # 第一段：phase0→1→2→0
        before = spell.plan
        after = grade(before, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(spell, before, after, MASTERED)
        self.assertEqual(spell.mode, SpellMode.NORMAL)
        before, after = spell.plan, grade(spell.plan, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(spell, before, after, MASTERED)
        self.assertEqual(spell.cooldown, 2)  # 还在第二张目标，未走完段
        before, after = spell.plan, grade(spell.plan, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(spell, before, after, MASTERED)
        self.assertEqual(spell.cooldown, 1)
        self.assertEqual(spell.mode, SpellMode.NORMAL)

        # 第二段走完
        before, after = spell.plan, grade(spell.plan, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(spell, before, after, MASTERED)
        before, after = spell.plan, grade(spell.plan, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(spell, before, after, MASTERED)
        before, after = spell.plan, grade(spell.plan, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(spell, before, after, MASTERED)
        self.assertEqual(spell.cooldown, 0)
        self.assertEqual(spell.mode, SpellMode.INVITE)

        # 冷却中托盘仍可开始
        cooling = replace(empty_spell(sealed()), cooldown=2, tray_unlocked=True)
        started = start_from_tray(cooling, MASTERED)
        self.assertEqual(started.mode, SpellMode.SPELLING)
        self.assertEqual(started.cooldown, 2)

    def test_mute_blocks_auto_invite(self) -> None:
        plan = sealed(phase=2, current="theme", queue=("cat", "dog", "apple", "book"))
        spell = replace(empty_spell(plan), mode=SpellMode.INVITE, tray_unlocked=True)
        spell = mute_invite(spell)
        self.assertTrue(spell.mute_invite)
        after = grade(plan, True, CATALOG, MASTERED, random.Random(0))
        spell = after_plan_change(replace(spell, plan=plan), plan, after, MASTERED)
        self.assertEqual(spell.mode, SpellMode.NORMAL)

    def test_end_spelling_sets_cooldown_and_keeps_current(self) -> None:
        plan = sealed(current="book", phase=1, queue=("book", "cat", "dog", "apple"))
        spell = replace(empty_spell(plan), mode=SpellMode.SPELLING)
        spell = advance_spelling(spell, CATALOG, MASTERED, random.Random(0))
        current = spell.plan.current
        spell = end_spelling(spell)
        self.assertEqual(spell.mode, SpellMode.NORMAL)
        self.assertEqual(spell.cooldown, 2)
        self.assertEqual(spell.plan.current, current)

    def test_spell_review_only_picks_mastered(self) -> None:
        plan = sealed(phase=1, current="book", queue=("book", "cat", "dog", "apple"))
        spell = replace(empty_spell(plan), mode=SpellMode.SPELLING)
        spell = advance_spelling(spell, CATALOG, MASTERED, random.Random(0))
        self.assertEqual(spell.plan.phase, 2)
        self.assertEqual(spell.plan.current, "theme")
        self.assertNotEqual(spell.plan.current, "extra")

    def test_spell_review_falls_back_to_target_without_weak_words(self) -> None:
        # 只有名单内词，没有达标熟词
        progress = {w: (9, 10) for w in FOUR}
        plan = sealed(phase=1, current="book", queue=("book", "cat", "dog", "apple"))
        spell = replace(empty_spell(plan), mode=SpellMode.SPELLING)
        spell = advance_spelling(spell, FOUR, progress, random.Random(0))
        self.assertEqual(spell.plan.phase, 0)
        self.assertEqual(spell.plan.current, "cat")

    def test_accept_invite_clears_cooldown(self) -> None:
        spell = replace(
            empty_spell(sealed()),
            mode=SpellMode.INVITE,
            cooldown=2,
            tray_unlocked=True,
        )
        spell = accept_invite(spell)
        self.assertEqual(spell.mode, SpellMode.SPELLING)
        self.assertEqual(spell.cooldown, 0)

    def test_misses_open_example_at_six(self) -> None:
        spell = replace(empty_spell(sealed()), mode=SpellMode.SPELLING)
        for _ in range(MISS_LIMIT - 1):
            spell = register_miss(spell)
        self.assertFalse(spell.example_open)
        self.assertEqual(spell.miss_count, MISS_LIMIT - 1)
        spell = register_miss(spell)
        self.assertTrue(spell.example_open)
        self.assertEqual(spell.miss_count, MISS_LIMIT)

    def test_skip_while_example_open_advances(self) -> None:
        plan = sealed()
        first = plan.current
        spell = replace(
            empty_spell(plan),
            mode=SpellMode.SPELLING,
            miss_count=6,
            example_open=True,
        )
        spell = advance_spelling(spell, FOUR, MASTERED)
        self.assertEqual(spell.miss_count, 0)
        self.assertFalse(spell.example_open)
        self.assertNotEqual(spell.plan.current, first)

    def test_cells_and_assemble_keep_punctuation(self) -> None:
        cells = cells_for("CD-ROM")
        self.assertEqual([c.fixed for c in cells], [False, False, True, False, False, False])
        self.assertEqual(cells[2].text, "-")
        built = assemble_answer("CD-ROM", ["c", "d", "r", "o", "m"])
        self.assertTrue(answers_match("CD-ROM", built))
        phrase = assemble_answer("account for", list("accountfor"))
        self.assertTrue(answers_match("account for", phrase))

    def test_new_day_clears_spell_flags(self) -> None:
        spell = replace(
            empty_spell(sealed()),
            mute_invite=True,
            cooldown=2,
            tray_unlocked=True,
            mode=SpellMode.SPELLING,
            miss_count=3,
        )
        spell = ensure_spell_day(spell, "2026-10-14")
        self.assertEqual(spell.plan.day, "2026-10-14")
        self.assertEqual(spell.plan.collected, ())
        self.assertFalse(spell.mute_invite)
        self.assertEqual(spell.cooldown, 0)
        self.assertFalse(spell.tray_unlocked)
        self.assertEqual(spell.mode, SpellMode.NORMAL)
        self.assertEqual(spell.plan.current, "apple")


if __name__ == "__main__":
    unittest.main()
