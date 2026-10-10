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
    slain: Sequence[str] = (),
) -> DailyPlan:
    if plan.current is None:
        return plan
    word = plan.current.casefold()
    blocked = _as_slain(slain)
    if not plan.sealed:
        collected = list(plan.collected)
        if not known and word not in collected:
            collected.append(word)
        collected_t = tuple(collected)
        next_plan = replace(plan, collected=collected_t, current=word)
        if len(collected_t) >= plan.goal:
            return _seal(next_plan, catalog, progress, rng, blocked)
        picked = _pick_weighted(catalog, progress, (word,), rng, blocked)
        if picked is None and word not in blocked:
            picked = word
        return replace(next_plan, current=picked)

    if plan.phase in (0, 1):
        queue = _rotate(plan.queue, word)
        if plan.phase == 0:
            shown = _first_showable(queue, catalog, blocked)
            if shown is None and word not in blocked:
                shown = word
            return replace(plan, queue=queue, phase=1, current=shown)
        review = _pick_review_or_fallback(catalog, progress, plan.collected, word, rng, blocked)
        if review is not None:
            return replace(plan, queue=queue, phase=2, current=review)
        return replace(plan, queue=queue, phase=0, current=_first_showable(queue, catalog, blocked))

    return replace(plan, phase=0, current=_first_showable(plan.queue, catalog, blocked))


def set_goal(
    plan: DailyPlan,
    goal: int,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
    slain: Sequence[str] = (),
) -> DailyPlan:
    new_goal = clamp_goal(goal)
    if new_goal == plan.goal:
        return plan
    blocked = _as_slain(slain)
    was_sealed = plan.sealed
    collected = plan.collected[:new_goal]
    removed = set(plan.collected[len(collected) :])
    queue = tuple(item for item in plan.queue if item not in removed)
    next_plan = replace(plan, goal=new_goal, collected=collected, queue=queue)
    now_sealed = next_plan.sealed
    if not was_sealed and now_sealed:
        return _seal(next_plan, catalog, progress, rng, blocked)
    if was_sealed and not now_sealed:
        return replace(next_plan, queue=(), phase=0)
    if was_sealed and now_sealed:
        if _goal_keeps_current(plan, collected, blocked):
            return replace(next_plan, current=plan.current, phase=plan.phase)
        return replace(
            next_plan,
            current=_first_showable(queue, catalog, blocked),
            phase=plan.phase,
        )
    return replace(next_plan, current=plan.current)


def switch_catalog(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
    slain: Sequence[str] = (),
) -> DailyPlan:
    if _current_available(plan, catalog, slain):
        return plan
    return _replace_unavailable(plan, catalog, progress, slain, rng)


def resolve_current(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
    slain: Sequence[str] = (),
) -> DailyPlan:
    if _current_available(plan, catalog, slain):
        return plan
    return switch_catalog(plan, catalog, progress, rng, slain)


def slay(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    slain: Sequence[str],
    rng: Optional[random.Random] = None,
) -> DailyPlan:
    """当前词已斩杀。名单和队列的成员不变，下一张跳过已斩杀的词。没有可抽的词时 current 为空，表示收完卡。"""
    blocked = _as_slain(slain)
    if plan.current is not None:
        blocked.add(plan.current.casefold())
    return _replace_unavailable(plan, catalog, progress, blocked, rng)


def restore(
    plan: DailyPlan,
    word: str,
    catalog: Sequence[str],
    progress: Progress,
    slain: Sequence[str] = (),
    rng: Optional[random.Random] = None,
) -> DailyPlan:
    """恢复一个词。当前卡不变；若它还在今天的名单里，从队列队尾重新参加轮换。收完卡则再抽一张。"""
    key = word.casefold()
    queue = plan.queue
    if plan.sealed and key in plan.collected:
        queue = tuple(item for item in plan.queue if item != key) + (key,)
    updated = replace(plan, queue=queue)
    if plan.current is not None:
        return updated
    return resolve_current(updated, catalog, progress, rng, slain)


def _goal_keeps_current(plan: DailyPlan, collected: Sequence[str], slain: set[str]) -> bool:
    if plan.current is not None and plan.current in slain:
        return False
    if plan.phase == 2:
        return True
    return plan.current is not None and plan.current in collected


def _replace_unavailable(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    slain: Sequence[str],
    rng: Optional[random.Random],
) -> DailyPlan:
    if not plan.sealed:
        return replace(plan, current=_pick_weighted(catalog, progress, (), rng, slain))
    if plan.phase in (0, 1):
        showable = _first_showable(plan.queue, catalog, slain)
        if showable is not None:
            return replace(plan, current=showable)
        review = _pick_review_or_fallback(catalog, progress, plan.collected, plan.current, rng, slain)
        if review is not None:
            return replace(plan, current=review, phase=2)
        return replace(plan, current=None)
    review = _pick_review_or_fallback(catalog, progress, plan.collected, plan.current, rng, slain)
    if review is not None:
        return replace(plan, current=review, phase=2)
    showable = _first_showable(plan.queue, catalog, slain)
    if showable is not None:
        return replace(plan, current=showable, phase=0)
    return replace(plan, current=None)


def _current_available(plan: DailyPlan, catalog: Sequence[str], slain: Sequence[str]) -> bool:
    if plan.current is None:
        return False
    key = plan.current.casefold()
    return key in _present(catalog) and key not in _as_slain(slain)


def _seal(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random],
    slain: Sequence[str],
) -> DailyPlan:
    queue = plan.collected
    showable = _first_showable(queue, catalog, slain)
    if showable is not None:
        return replace(plan, queue=queue, phase=0, current=showable)
    review = _pick_review_or_fallback(catalog, progress, plan.collected, plan.current, rng, slain)
    if review is not None:
        return replace(plan, queue=queue, phase=2, current=review)
    return replace(plan, queue=queue, phase=0, current=None)


def _pick_review_or_fallback(
    catalog: Sequence[str],
    progress: Progress,
    collected: Sequence[str],
    current: Optional[str],
    rng: Optional[random.Random],
    slain: Sequence[str] = (),
) -> Optional[str]:
    review = _pick_review(catalog, progress, collected, current, rng, slain)
    if review is not None:
        return review
    exclude = list(collected)
    if current is not None:
        exclude.append(current)
    return _pick_weighted(catalog, progress, exclude, rng, slain)


def _pick_review(
    catalog: Sequence[str],
    progress: Progress,
    collected: Sequence[str],
    current: Optional[str],
    rng: Optional[random.Random],
    slain: Sequence[str] = (),
) -> Optional[str]:
    blocked = {item.casefold() for item in collected}
    blocked.update(_as_slain(slain))
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
    slain: Sequence[str] = (),
) -> Optional[str]:
    blocked = list(exclude)
    blocked.extend(slain)
    return pick_one(_candidates(catalog, progress), exclude=blocked, rng=rng)


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


def _first_showable(
    queue: Sequence[str],
    catalog: Sequence[str],
    slain: Sequence[str] = (),
) -> Optional[str]:
    present = _present(catalog)
    blocked = _as_slain(slain)
    for item in queue:
        key = item.casefold()
        if key in present and key not in blocked:
            return item
    return None


def _rotate(queue: Sequence[str], word: str) -> tuple[str, ...]:
    key = word.casefold()
    items = [item for item in queue if item != key]
    items.append(key)
    return tuple(items)


def _present(catalog: Sequence[str]) -> set[str]:
    return {item.casefold() for item in catalog}


def _as_slain(slain: Sequence[str]) -> set[str]:
    return {item.casefold() for item in slain}


def _key(word: Optional[str]) -> Optional[str]:
    if word is None:
        return None
    return word.casefold()
