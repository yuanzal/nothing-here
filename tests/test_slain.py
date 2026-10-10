from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from nothing_here.domain.daily import DailyPlan, grade, resolve_current, restore, slay
from nothing_here.storage.db import Store

DAY = "2026-10-10"
CATALOG = ["apple", "book", "cat", "dog", "theme"]
REVIEW = {"theme": (1, 1)}


def plan(**kwargs: object) -> DailyPlan:
    values: dict[str, object] = dict(
        goal=4,
        day=DAY,
        collected=(),
        queue=(),
        phase=0,
        current=None,
    )
    values.update(kwargs)
    return DailyPlan(**values)  # type: ignore[arg-type]


class SlainTests(unittest.TestCase):
    def test_slain_word_is_not_drawn(self) -> None:
        catalog = ["alpha", "beta", "gamma"]
        progress = {"alpha": (0, 20)}
        state = plan(goal=100, current="gamma")
        rng = random.Random(1)
        for _ in range(30):
            state = grade(state, True, catalog, progress, rng, slain=["alpha"])
            self.assertNotEqual(state.current, "alpha")

        replaced = resolve_current(
            plan(goal=100, current="alpha"),
            ["alpha", "beta"],
            {},
            slain=["alpha"],
        )
        self.assertEqual(replaced.current, "beta")

    def test_slay_does_not_change_scores(self) -> None:
        progress = {"apple": (2, 5)}
        slay(plan(goal=10, current="apple"), ["apple", "book"], progress, ["apple"])
        self.assertEqual(progress, {"apple": (2, 5)})

        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "study.db")
            store.record("apple", True)
            store.record("apple", False)
            store.slay_word("Apple")
            store.slay_word("book")
            self.assertEqual(store.get_progress("apple"), (1, 2))
            self.assertEqual(store.get_progress("book"), (0, 0))
            listed = store.list_slain()
            self.assertEqual([word for word, _at in listed], ["book", "apple"])
            self.assertGreater(listed[0][1], listed[1][1])
            store.restore_word("book")
            self.assertEqual([word for word, _at in store.list_slain()], ["apple"])
            self.assertEqual(store.get_progress("apple"), (1, 2))
            store.close()

    def test_slay_keeps_the_list_and_skips_a_queued_word(self) -> None:
        state = plan(
            collected=("apple", "book", "cat", "dog"),
            queue=("apple", "book", "cat", "dog"),
            phase=0,
            current="apple",
        )
        slain = slay(state, CATALOG, REVIEW, ["apple"])
        self.assertEqual(slain.collected, state.collected)
        self.assertEqual(slain.queue, state.queue)
        self.assertEqual(slain.current, "book")

        skipped = grade(state, True, CATALOG, REVIEW, random.Random(0), slain=["book"])
        self.assertEqual(skipped.collected, state.collected)
        self.assertEqual(skipped.queue, ("book", "cat", "dog", "apple"))
        self.assertEqual(skipped.current, "cat")
        self.assertIn("book", skipped.queue)

    def test_restore_puts_a_listed_word_at_the_tail_and_can_draw_it(self) -> None:
        state = plan(
            collected=("apple", "book", "cat", "dog"),
            queue=("apple", "book", "cat", "dog"),
            phase=0,
            current="apple",
        )
        restored = restore(state, "book", CATALOG, REVIEW, slain=[])
        self.assertEqual(restored.current, "apple")
        self.assertEqual(restored.collected, state.collected)
        self.assertEqual(restored.queue, ("apple", "cat", "dog", "book"))

        drawn = restore(plan(goal=10, current=None), "theme", ["theme"], {}, slain=[])
        self.assertEqual(drawn.current, "theme")

    def test_finished_card_when_nothing_unslain_can_be_drawn(self) -> None:
        result = slay(plan(goal=10, current="apple"), ["apple"], {}, ["apple"])
        self.assertIsNone(result.current)

        again = resolve_current(
            plan(goal=10, current="apple"),
            ["apple", "book"],
            {},
            slain=["apple", "book"],
        )
        self.assertIsNone(again.current)
