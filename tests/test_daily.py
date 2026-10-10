from __future__ import annotations

import random
import unittest
from dataclasses import replace

from nothing_here.domain.daily import DailyPlan, ensure_day, grade, set_goal, switch_catalog

DAY = "2026-10-10"
CATALOG = ["apple", "book", "cat", "dog", "theme"]
FOUR = ["apple", "book", "cat", "dog"]
REVIEW = {"theme": (1, 1)}


def plan(**kwargs: object) -> DailyPlan:
    values = dict(
        goal=4,
        day=DAY,
        collected=(),
        queue=(),
        phase=0,
        current=None,
    )
    values.update(kwargs)
    return DailyPlan(**values)  # type: ignore[arg-type]


def mark(state: DailyPlan, word: str, known: bool = False, **kwargs: object) -> DailyPlan:
    catalog = kwargs.pop("catalog", CATALOG)
    progress = kwargs.pop("progress", REVIEW)
    rng = kwargs.pop("rng", random.Random(0))
    return grade(replace(state, current=word), known, catalog, progress, rng)


class DailyTests(unittest.TestCase):
    def test_collecting_does_not_enter_target_rotation(self) -> None:
        state = mark(plan(current="apple"), "apple")
        state = mark(state, "book")
        self.assertFalse(state.sealed)
        self.assertEqual(state.collected, ("apple", "book"))
        self.assertEqual(state.phase, 0)
        self.assertEqual(state.queue, ())

    def test_known_does_not_change_the_list(self) -> None:
        state = mark(plan(current="apple"), "apple", known=True)
        self.assertEqual(state.collected, ())
        self.assertFalse(state.sealed)

    def test_unknown_occupies_one_slot(self) -> None:
        state = mark(plan(current="apple"), "apple")
        state = mark(state, "apple")
        self.assertEqual(state.collected, ("apple",))

    def test_seal_shows_the_earliest_target(self) -> None:
        state = plan(current="apple")
        for word in FOUR:
            state = mark(state, word)
        self.assertTrue(state.sealed)
        self.assertEqual(state.collected, ("apple", "book", "cat", "dog"))
        self.assertEqual(state.queue, ("apple", "book", "cat", "dog"))
        self.assertEqual(state.current, "apple")
        self.assertEqual(state.phase, 0)

    def test_sealed_order_is_two_targets_then_review(self) -> None:
        state = plan(current="apple")
        for word in FOUR:
            state = mark(state, word)
        state = grade(state, True, CATALOG, REVIEW, random.Random(0))
        self.assertEqual((state.current, state.phase), ("book", 1))
        self.assertEqual(state.queue, ("book", "cat", "dog", "apple"))

        state = grade(state, True, CATALOG, REVIEW, random.Random(0))
        self.assertEqual((state.current, state.phase), ("theme", 2))

        state = grade(state, True, CATALOG, REVIEW, random.Random(0))
        self.assertEqual((state.current, state.phase), ("cat", 0))

        state = grade(state, True, CATALOG, REVIEW, random.Random(0))
        self.assertEqual((state.current, state.phase), ("dog", 1))

        state = grade(state, True, CATALOG, REVIEW, random.Random(0))
        self.assertEqual((state.current, state.phase), ("theme", 2))

    def test_missing_review_uses_the_next_target_as_phase_zero(self) -> None:
        state = plan(current="apple")
        for word in FOUR:
            state = mark(state, word, catalog=FOUR, progress={})
        state = grade(state, True, FOUR, {}, random.Random(0))
        self.assertEqual((state.current, state.phase), ("book", 1))

        state = grade(state, True, FOUR, {}, random.Random(0))
        self.assertEqual((state.current, state.phase), ("cat", 0))

        state = grade(state, True, FOUR, {}, random.Random(0))
        self.assertEqual((state.current, state.phase), ("dog", 1))

        state = grade(state, True, FOUR, {}, random.Random(0))
        self.assertEqual((state.current, state.phase), ("apple", 0))

    def test_changing_goal_to_collected_count_seals(self) -> None:
        state = plan(goal=4, collected=("apple", "book"), current="theme")
        state = set_goal(state, 2, CATALOG, REVIEW)
        self.assertTrue(state.sealed)
        self.assertEqual(state.queue, ("apple", "book"))
        self.assertEqual(state.current, "apple")
        self.assertEqual(state.phase, 0)

    def test_shrinking_goal_drops_later_words_and_keeps_phase(self) -> None:
        state = plan(
            collected=("apple", "book", "cat", "dog"),
            queue=("dog", "apple", "book", "cat"),
            phase=1,
            current="dog",
        )
        state = set_goal(state, 3, CATALOG, REVIEW)
        self.assertEqual(state.collected, ("apple", "book", "cat"))
        self.assertEqual(state.queue, ("apple", "book", "cat"))
        self.assertEqual(state.current, "apple")
        self.assertEqual(state.phase, 1)

    def test_growing_goal_unseals_then_reseals_in_collect_order(self) -> None:
        state = plan(
            collected=("apple", "book", "cat", "dog"),
            queue=("book", "cat", "dog", "apple"),
            phase=1,
            current="book",
        )
        catalog = CATALOG + ["egg", "fog"]
        state = set_goal(state, 6, catalog, REVIEW)
        self.assertFalse(state.sealed)
        self.assertEqual(state.current, "book")
        state = mark(state, "egg", catalog=catalog)
        state = mark(state, "fog", catalog=catalog)
        self.assertTrue(state.sealed)
        self.assertEqual(state.collected, ("apple", "book", "cat", "dog", "egg", "fog"))
        self.assertEqual(state.queue, ("apple", "book", "cat", "dog", "egg", "fog"))
        self.assertEqual(state.current, "apple")
        self.assertEqual(state.phase, 0)

    def test_new_day_clears_lists_and_keeps_the_word(self) -> None:
        state = plan(
            day="2026-10-09",
            collected=("apple", "book"),
            queue=("apple", "book"),
            current="theme",
        )
        state = ensure_day(state, DAY)
        self.assertEqual(state.day, DAY)
        self.assertEqual(state.collected, ())
        self.assertEqual(state.queue, ())
        self.assertEqual(state.current, "theme")
        self.assertEqual(state.phase, 0)

    def test_missing_catalog_words_stay_in_the_queue(self) -> None:
        state = plan(
            collected=("apple", "book", "cat", "dog"),
            queue=("apple", "book", "cat", "dog"),
            phase=0,
            current="apple",
        )
        state = switch_catalog(state, ["book", "theme"], REVIEW)
        self.assertEqual(state.current, "book")
        self.assertEqual(state.phase, 0)
        self.assertEqual(state.queue, ("apple", "book", "cat", "dog"))
        self.assertEqual(state.collected, ("apple", "book", "cat", "dog"))


if __name__ == "__main__":
    unittest.main()
