from __future__ import annotations

import unittest

from nothing_here.domain.weight import WEIGHT_MAX, WEIGHT_MIN, accuracy_percent, weight


class WeightTests(unittest.TestCase):
    def test_table_from_spec(self) -> None:
        cases = [
            (0, 0, 1.0),
            (1, 1, 0.5),
            (0, 1, 2.0),
            (10, 10, 0.090909),
            (0, 10, 8.0),
            (5, 10, 1.0),
            (16, 20, 0.160942),
            (4, 20, 6.213432),
            (0, 7, 8.0),
            (19, 19, 0.05),
            (100, 100, 0.05),
        ]
        for correct, reviews, expected in cases:
            with self.subTest(correct=correct, reviews=reviews):
                self.assertAlmostEqual(weight(correct, reviews), expected, delta=1e-6)

    def test_unseen_is_one(self) -> None:
        self.assertEqual(weight(0, 0), 1.0)

    def test_clamps_to_documented_bounds(self) -> None:
        self.assertAlmostEqual(weight(0, 7), WEIGHT_MAX, delta=1e-6)
        self.assertAlmostEqual(weight(0, 100), WEIGHT_MAX, delta=1e-6)
        self.assertAlmostEqual(weight(19, 19), WEIGHT_MIN, delta=1e-6)
        self.assertAlmostEqual(weight(100, 100), WEIGHT_MIN, delta=1e-6)
        self.assertLessEqual(weight(0, 100), WEIGHT_MAX)
        self.assertGreaterEqual(weight(19, 19), WEIGHT_MIN)

    def test_accuracy_percent(self) -> None:
        self.assertIsNone(accuracy_percent(0, 0))
        self.assertEqual(accuracy_percent(1, 3), 33)
        self.assertEqual(accuracy_percent(2, 3), 67)
        self.assertEqual(accuracy_percent(1, 8), 13)


if __name__ == "__main__":
    unittest.main()
