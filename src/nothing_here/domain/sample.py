from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class WeightedWord:
    word: str
    weight: float


def pick_one(
    candidates: Sequence[WeightedWord],
    exclude: Sequence[str] = (),
    rng: Optional[random.Random] = None,
) -> Optional[str]:
    excluded = {item.casefold() for item in exclude}
    pool = [item for item in candidates if item.word.casefold() not in excluded]
    if not pool:
        return None
    chooser = rng if rng is not None else random.Random()
    picked = chooser.choices(pool, weights=[item.weight for item in pool], k=1)[0]
    return picked.word
