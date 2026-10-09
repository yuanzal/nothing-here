from __future__ import annotations

import random
import unittest

from nothing_here.domain.sample import WeightedWord, pick_one


class SampleTests(unittest.TestCase):
    def test_excludes_caller_words(self) -> None:
        candidates = [
            WeightedWord("alpha", 1.0),
            WeightedWord("beta", 1.0),
            WeightedWord("gamma", 1.0),
        ]
        rng = random.Random(0)
        for _ in range(40):
            picked = pick_one(candidates, exclude=["BETA", "gamma"], rng=rng)
            self.assertEqual(picked, "alpha")

    def test_empty_pool_returns_none(self) -> None:
        self.assertIsNone(pick_one([], exclude=[]))
        self.assertIsNone(
            pick_one(
                [WeightedWord("only", 1.0)],
                exclude=["only"],
            )
        )

    def test_single_candidate_is_always_chosen(self) -> None:
        candidates = [WeightedWord("solo", 0.05)]
        for seed in range(20):
            self.assertEqual(
                pick_one(candidates, exclude=[], rng=random.Random(seed)),
                "solo",
            )

    def test_higher_weight_is_drawn_more_often(self) -> None:
        candidates = [
            WeightedWord("low-a", 1.0),
            WeightedWord("low-b", 1.0),
            WeightedWord("high", 8.0),
        ]
        rng = random.Random(1)
        counts = {"low-a": 0, "low-b": 0, "high": 0}
        n = 5000
        for _ in range(n):
            picked = pick_one(candidates, exclude=[], rng=rng)
            assert picked is not None
            counts[picked] += 1
        self.assertGreater(counts["high"], counts["low-a"])
        self.assertGreater(counts["high"], counts["low-b"])
        self.assertGreater(counts["high"], n * 0.5)


if __name__ == "__main__":
    unittest.main()
