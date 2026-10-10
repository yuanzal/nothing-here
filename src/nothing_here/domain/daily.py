from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Mapping, Optional, Sequence

from nothing_here.domain.sample import WeightedWord, pick_one
from nothing_here.domain.weight import weight

GOAL_MIN = 2
GOAL_MAX = 100
GOAL_DEFAULT = 10

Progress = Mapping[str, tuple[int, int]]


@dataclass(frozen=True)
class DailyPlan:
    goal: int
    day: str
    collected: tuple[str, ...]
    queue: tuple[str, ...]
    phase: int
    current: Optional[str]

    @property
    def sealed(self) -> bool:
        return len(self.collected) >= self.goal

    @property
    def count(self) -> int:
        return len(self.collected)


def clamp_goal(n: int) -> int:
    return min(GOAL_MAX, max(GOAL_MIN, int(n)))


def empty_plan(day: str, goal: int = GOAL_DEFAULT, current: Optional[str] = None) -> DailyPlan:
    return DailyPlan(clamp_goal(goal), day, (), (), 0, _key(current))


def ensure_day(plan: DailyPlan, today: str) -> DailyPlan:
    if plan.day == today:
        return plan
    return DailyPlan(plan.goal, today, (), (), 0, plan.current)


def grade(
    plan: DailyPlan,
    known: bool,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
) -> DailyPlan:
    if plan.current is None:
        return plan
    word = plan.current.casefold()
    if not plan.sealed:
        collected = list(plan.collected)
        if not known and word not in collected:
            collected.append(word)
        collected_t = tuple(collected)
        next_plan = replace(plan, collected=collected_t, current=word)
        if len(collected_t) >= plan.goal:
            return _seal(next_plan, catalog, progress, rng)
        picked = _pick_weighted(catalog, progress, (word,), rng)
        return replace(next_plan, current=picked or word)

    if plan.phase in (0, 1):
        queue = _rotate(plan.queue, word)
        if plan.phase == 0:
            return replace(plan, queue=queue, phase=1, current=_first_showable(queue, catalog) or word)
        review = _pick_review_or_fallback(catalog, progress, plan.collected, word, rng)
        if review is not None:
            return replace(plan, queue=queue, phase=2, current=review)
        return replace(plan, queue=queue, phase=0, current=_first_showable(queue, catalog))

    return replace(plan, phase=0, current=_first_showable(plan.queue, catalog))


def set_goal(
    plan: DailyPlan,
    goal: int,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
) -> DailyPlan:
    new_goal = clamp_goal(goal)
    if new_goal == plan.goal:
        return plan
    was_sealed = plan.sealed
    collected = plan.collected[:new_goal]
    removed = set(plan.collected[len(collected) :])
    queue = tuple(item for item in plan.queue if item not in removed)
    next_plan = replace(plan, goal=new_goal, collected=collected, queue=queue)
    now_sealed = next_plan.sealed
    if not was_sealed and now_sealed:
        return _seal(next_plan, catalog, progress, rng)
    if was_sealed and not now_sealed:
        return replace(next_plan, queue=(), phase=0)
    if was_sealed and now_sealed:
        if plan.phase == 2 or (plan.current is not None and plan.current in collected):
            return replace(next_plan, current=plan.current, phase=plan.phase)
        return replace(
            next_plan,
            current=_first_showable(queue, catalog),
            phase=plan.phase,
        )
    return replace(next_plan, current=plan.current)


def switch_catalog(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
) -> DailyPlan:
    present = _present(catalog)
    if plan.current is not None and plan.current in present:
        return plan
    if not plan.sealed:
        return replace(plan, current=_pick_weighted(catalog, progress, (), rng))
    if plan.phase in (0, 1):
        showable = _first_showable(plan.queue, catalog)
        if showable is not None:
            return replace(plan, current=showable)
        review = _pick_review_or_fallback(catalog, progress, plan.collected, plan.current, rng)
        if review is not None:
            return replace(plan, current=review, phase=2)
        return replace(plan, current=None)
    review = _pick_review_or_fallback(catalog, progress, plan.collected, plan.current, rng)
    if review is not None:
        return replace(plan, current=review, phase=2)
    showable = _first_showable(plan.queue, catalog)
    if showable is not None:
        return replace(plan, current=showable, phase=0)
    return replace(plan, current=None)


def resolve_current(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
) -> DailyPlan:
    present = _present(catalog)
    if plan.current is not None and plan.current in present:
        return plan
    return switch_catalog(plan, catalog, progress, rng)


def _seal(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random],
) -> DailyPlan:
    queue = plan.collected
    showable = _first_showable(queue, catalog)
    if showable is not None:
        return replace(plan, queue=queue, phase=0, current=showable)
    review = _pick_review_or_fallback(catalog, progress, plan.collected, plan.current, rng)
    if review is not None:
        return replace(plan, queue=queue, phase=2, current=review)
    return replace(plan, queue=queue, phase=0, current=None)


def _pick_review_or_fallback(
    catalog: Sequence[str],
    progress: Progress,
    collected: Sequence[str],
    current: Optional[str],
    rng: Optional[random.Random],
) -> Optional[str]:
    review = _pick_review(catalog, progress, collected, current, rng)
    if review is not None:
        return review
    exclude = list(collected)
    if current is not None:
        exclude.append(current)
    return _pick_weighted(catalog, progress, exclude, rng)


def _pick_review(
    catalog: Sequence[str],
    progress: Progress,
    collected: Sequence[str],
    current: Optional[str],
    rng: Optional[random.Random],
) -> Optional[str]:
    blocked = {item.casefold() for item in collected}
    if current is not None:
        blocked.add(current.casefold())
    pool: list[WeightedWord] = []
    seen: set[str] = set()
    for raw in catalog:
        key = raw.casefold()
        if key in seen or key in blocked:
            continue
        seen.add(key)
        value = weight(*progress.get(key, (0, 0)))
        if value < 1:
            pool.append(WeightedWord(key, 1.0 / value))
    return pick_one(pool, rng=rng)


def _pick_weighted(
    catalog: Sequence[str],
    progress: Progress,
    exclude: Sequence[str],
    rng: Optional[random.Random],
) -> Optional[str]:
    return pick_one(_candidates(catalog, progress), exclude=exclude, rng=rng)


def _candidates(catalog: Sequence[str], progress: Progress) -> list[WeightedWord]:
    items: list[WeightedWord] = []
    seen: set[str] = set()
    for raw in catalog:
        key = raw.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(WeightedWord(key, weight(*progress.get(key, (0, 0)))))
    return items


def _first_showable(queue: Sequence[str], catalog: Sequence[str]) -> Optional[str]:
    present = _present(catalog)
    for item in queue:
        if item in present:
            return item
    return None


def _rotate(queue: Sequence[str], word: str) -> tuple[str, ...]:
    key = word.casefold()
    items = [item for item in queue if item != key]
    items.append(key)
    return tuple(items)


def _present(catalog: Sequence[str]) -> set[str]:
    return {item.casefold() for item in catalog}


def _key(word: Optional[str]) -> Optional[str]:
    if word is None:
        return None
    return word.casefold()
