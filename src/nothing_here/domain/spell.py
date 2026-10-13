"""拼写邀请与拼写测试的纯规则。"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional, Sequence

from nothing_here.domain.daily import DailyPlan, Progress
from nothing_here.domain.sample import WeightedWord, pick_one
from nothing_here.domain.weight import weight

MISS_LIMIT = 6
_FIXED = frozenset(" -'")


class SpellMode(Enum):
    NORMAL = "normal"
    INVITE = "invite"
    SPELLING = "spelling"


@dataclass(frozen=True)
class SpellCell:
    """一格：fixed 为标点/空格时 text 是该字符；字母位 fixed=False 时 text 为空串。"""

    text: str
    fixed: bool


@dataclass(frozen=True)
class SpellState:
    plan: DailyPlan
    mode: SpellMode = SpellMode.NORMAL
    cooldown: int = 0
    mute_invite: bool = False
    tray_unlocked: bool = False
    miss_count: int = 0
    example_open: bool = False


def is_mastered(correct: int, reviews: int) -> bool:
    return reviews >= 1 and correct / reviews > 0.8


def collected_all_mastered(plan: DailyPlan, progress: Progress) -> bool:
    if not plan.sealed or not plan.collected:
        return False
    for word in plan.collected:
        correct, reviews = progress.get(word.casefold(), (0, 0))
        if not is_mastered(correct, reviews):
            return False
    return True


def invite_threshold(plan: DailyPlan, progress: Progress) -> bool:
    return collected_all_mastered(plan, progress) and plan.current is not None


def empty_spell(plan: DailyPlan) -> SpellState:
    return SpellState(plan=plan)


def ensure_spell_day(state: SpellState, today: str) -> SpellState:
    if state.plan.day == today:
        return state
    plan = DailyPlan(state.plan.goal, today, (), (), 0, state.plan.current)
    return SpellState(plan=plan)


def cycle_completed(before: DailyPlan, after: DailyPlan) -> bool:
    """一段「目标 → 目标 → 熟词」走完：从熟词拍回到 0，或第二张目标拍替补成目标。"""
    if before.phase == 2 and after.phase == 0:
        return True
    if before.phase == 1 and after.phase == 0:
        return True
    return False


def after_plan_change(
    state: SpellState,
    before: DailyPlan,
    after: DailyPlan,
    progress: Progress,
    *,
    consider_invite: bool = True,
) -> SpellState:
    """日常 plan 已更新后，处理冷却、托盘解锁、是否插入邀请。"""
    cooldown = state.cooldown
    if cooldown > 0 and cycle_completed(before, after):
        cooldown = max(0, cooldown - 1)
    tray = state.tray_unlocked or invite_threshold(after, progress)
    mode = SpellMode.NORMAL
    miss_count = 0
    example_open = False
    if not consider_invite and state.mode is SpellMode.SPELLING:
        mode = SpellMode.SPELLING
        miss_count = state.miss_count
        example_open = state.example_open
    next_state = replace(
        state,
        plan=after,
        cooldown=cooldown,
        tray_unlocked=tray,
        mode=mode,
        miss_count=miss_count,
        example_open=example_open,
    )
    if not consider_invite:
        return next_state
    if _should_auto_invite(next_state, progress):
        return replace(next_state, mode=SpellMode.INVITE)
    return next_state


def decline_invite(state: SpellState) -> SpellState:
    if state.mode is not SpellMode.INVITE:
        return state
    return replace(state, mode=SpellMode.NORMAL, cooldown=2)


def mute_invite(state: SpellState) -> SpellState:
    if state.mode is not SpellMode.INVITE:
        return state
    return replace(state, mode=SpellMode.NORMAL, mute_invite=True, cooldown=0)


def accept_invite(state: SpellState) -> SpellState:
    if state.mode is not SpellMode.INVITE or state.plan.current is None:
        return state
    return replace(
        state,
        mode=SpellMode.SPELLING,
        cooldown=0,
        miss_count=0,
        example_open=False,
    )


def start_from_tray(state: SpellState, progress: Progress) -> SpellState:
    if state.mode is SpellMode.SPELLING:
        return state
    if not state.plan.sealed or state.plan.current is None:
        return state
    if not state.tray_unlocked and not invite_threshold(state.plan, progress):
        return state
    return replace(
        state,
        mode=SpellMode.SPELLING,
        miss_count=0,
        example_open=False,
        tray_unlocked=True,
    )


def end_spelling(state: SpellState) -> SpellState:
    if state.mode is not SpellMode.SPELLING:
        return state
    return replace(
        state,
        mode=SpellMode.NORMAL,
        cooldown=2,
        miss_count=0,
        example_open=False,
    )


def dismiss_invite_on_hide(state: SpellState) -> SpellState:
    """邀请挂着时隐藏：下次显示日常正面，不恢复邀请。"""
    if state.mode is not SpellMode.INVITE:
        return state
    return replace(state, mode=SpellMode.NORMAL)


def exit_spell_modes(state: SpellState) -> SpellState:
    """改 n / 换词库等：退出邀请或拼写，保留冷却与 mute / tray。"""
    if state.mode is SpellMode.NORMAL:
        return state
    return replace(state, mode=SpellMode.NORMAL, miss_count=0, example_open=False)


def register_miss(state: SpellState) -> SpellState:
    if state.mode is not SpellMode.SPELLING:
        return state
    misses = min(MISS_LIMIT, state.miss_count + 1)
    open_example = state.example_open or misses >= MISS_LIMIT
    return replace(state, miss_count=misses, example_open=open_example)


def toggle_example(state: SpellState) -> SpellState:
    if state.mode is not SpellMode.SPELLING:
        return state
    return replace(state, example_open=not state.example_open)


def answers_match(expected: str, typed: str) -> bool:
    return expected.casefold() == typed.casefold()


def cells_for(word: str) -> tuple[SpellCell, ...]:
    cells: list[SpellCell] = []
    for char in word:
        if char in _FIXED:
            cells.append(SpellCell(char, True))
        else:
            cells.append(SpellCell("", False))
    return tuple(cells)


def assemble_answer(word: str, letters: Sequence[str]) -> str:
    """把用户填的字母按格子拼回字符串；letters 只含可编辑位，顺序从左到右。"""
    out: list[str] = []
    letter_i = 0
    for char in word:
        if char in _FIXED:
            out.append(char)
        else:
            if letter_i >= len(letters):
                out.append("")
            else:
                out.append(letters[letter_i])
                letter_i += 1
    return "".join(out)


def advance_spelling(
    state: SpellState,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random] = None,
    slain: Sequence[str] = (),
) -> SpellState:
    """拼对后前进 queue/phase，不改 progress；熟词拍只抽达标词。"""
    if state.mode is not SpellMode.SPELLING or state.plan.current is None:
        return state
    plan = _advance_sealed_spell(state.plan, catalog, progress, rng, slain)
    return replace(
        state,
        plan=plan,
        miss_count=0,
        example_open=False,
        mode=SpellMode.SPELLING if plan.current is not None else SpellMode.NORMAL,
    )


def _should_auto_invite(state: SpellState, progress: Progress) -> bool:
    if state.mute_invite or state.cooldown > 0:
        return False
    return invite_threshold(state.plan, progress)


def _advance_sealed_spell(
    plan: DailyPlan,
    catalog: Sequence[str],
    progress: Progress,
    rng: Optional[random.Random],
    slain: Sequence[str],
) -> DailyPlan:
    word = plan.current.casefold()  # type: ignore[union-attr]
    blocked = {item.casefold() for item in slain}
    if plan.phase in (0, 1):
        queue = _queue_rotate(plan.queue, word)
        if plan.phase == 0:
            shown = _next_showable(queue, catalog, blocked)
            if shown is None and word not in blocked:
                shown = word
            return replace(plan, queue=queue, phase=1, current=shown)
        review = _pick_mastered_review(catalog, progress, plan.collected, word, rng, blocked)
        if review is not None:
            return replace(plan, queue=queue, phase=2, current=review)
        return replace(plan, queue=queue, phase=0, current=_next_showable(queue, catalog, blocked))
    return replace(plan, phase=0, current=_next_showable(plan.queue, catalog, blocked))


def _pick_mastered_review(
    catalog: Sequence[str],
    progress: Progress,
    collected: Sequence[str],
    current: Optional[str],
    rng: Optional[random.Random],
    slain: set[str],
) -> Optional[str]:
    blocked = {item.casefold() for item in collected}
    blocked.update(slain)
    if current is not None:
        blocked.add(current.casefold())
    pool: list[WeightedWord] = []
    seen: set[str] = set()
    for raw in catalog:
        key = raw.casefold()
        if key in seen or key in blocked:
            continue
        seen.add(key)
        correct, reviews = progress.get(key, (0, 0))
        if not is_mastered(correct, reviews):
            continue
        value = weight(correct, reviews)
        pool.append(WeightedWord(key, 1.0 / value))
    return pick_one(pool, rng=rng)


def _queue_rotate(queue: Sequence[str], word: str) -> tuple[str, ...]:
    key = word.casefold()
    items = [item for item in queue if item != key]
    items.append(key)
    return tuple(items)


def _next_showable(
    queue: Sequence[str],
    catalog: Sequence[str],
    slain: set[str],
) -> Optional[str]:
    present = {item.casefold() for item in catalog}
    for item in queue:
        key = item.casefold()
        if key in present and key not in slain:
            return item
    return None
