from __future__ import annotations

import math

WEIGHT_MIN = 0.05
WEIGHT_MAX = 8.0


def accuracy_percent(correct: int, reviews: int) -> int | None:
    if reviews == 0:
        return None
    return int(correct * 100 / reviews + 0.5)


def weight(correct: int, reviews: int) -> float:
    if reviews == 0:
        return 1.0
    mastery = 2.0 * correct / reviews - 1.0
    raw = math.exp(-mastery * math.log1p(reviews))
    return min(WEIGHT_MAX, max(WEIGHT_MIN, raw))
