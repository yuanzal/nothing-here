"""摸鱼计时的今日累计。不读文件，不访问网络，不排版。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping, Optional

CURRENCIES: tuple[str, ...] = ("CNY", "USD", "EUR", "JPY", "KRW", "SGD")
CURRENCY_LABELS: tuple[tuple[str, str], ...] = (
    ("CNY", "人民币"),
    ("USD", "美元"),
    ("EUR", "欧元"),
    ("JPY", "日元"),
    ("KRW", "韩元"),
    ("SGD", "新加坡元"),
)
SYMBOLS: dict[str, str] = {
    "CNY": "￥",
    "USD": "$",
    "EUR": "€",
    "JPY": "円",
    "KRW": "₩",
    "SGD": "S$",
}
ZERO_DECIMAL = frozenset({"JPY", "KRW"})
MONTHLY_DAYS = Decimal("21.75")
_AMOUNT_MAX = Decimal("999999999")


@dataclass(frozen=True)
class PaySettings:
    pay_mode: str
    daily_amount: Decimal
    monthly_amount: Decimal
    unit: str
    display: str
    work_start: Optional[int]
    work_end: Optional[int]
    lunch_start: Optional[int]
    lunch_end: Optional[int]


@dataclass(frozen=True)
class WorkCommit:
    """确定工作窗口后的四个时刻。ok 为假时调用方保持原值并留在窗口里。"""

    ok: bool
    work_start: Optional[int] = None
    work_end: Optional[int] = None
    lunch_start: Optional[int] = None
    lunch_end: Optional[int] = None


def parse_clock(text: str) -> Optional[int]:
    """「时:分」变成从本地零点起的分钟。对不上则返回 None。"""
    raw = text.strip()
    hour_text, sep, minute_text = raw.partition(":")
    if not sep or not hour_text.isdigit() or not minute_text.isdigit():
        return None
    if len(minute_text) != 2 or len(hour_text) > 2:
        return None
    hour = int(hour_text)
    minute = int(minute_text)
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def format_clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_amount(text: str, currency: str) -> Optional[Decimal]:
    """非负金额。日元和韩元只要整数，其余最多到分。"""
    raw = text.strip().replace(",", "")
    if not raw or currency not in CURRENCIES:
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    if amount < 0 or amount > _AMOUNT_MAX:
        return None
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int):
        return None
    if currency in ZERO_DECIMAL:
        if exponent < 0:
            return None
        return amount
    if exponent < -2:
        return None
    return amount


def commit_work_times(
    start_text: str,
    end_text: str,
    lunch_start_text: str,
    lunch_end_text: str,
) -> WorkCommit:
    """工作时段不成立则整单不保存。午休不成立则工作时段照常保存，午休视为没设。"""
    start = parse_clock(start_text)
    end = parse_clock(end_text)
    if start is None or end is None or start >= end:
        return WorkCommit(False)
    lunch = _accepted_lunch(start, end, lunch_start_text, lunch_end_text)
    if lunch is None:
        return WorkCommit(True, start, end, None, None)
    return WorkCommit(True, start, end, lunch[0], lunch[1])


def strip_text(
    settings: PaySettings,
    moment: datetime,
    per_eur: Optional[Mapping[str, Decimal]] = None,
) -> str:
    """薪条上的一行。午休期间是「休息中」，其余是「你已摸鱼」加金额。"""
    if _resting(settings, moment):
        return "休息中"
    amount = accrued(settings, moment)
    shown, currency = project(amount, settings.unit, settings.display, per_eur)
    return f"你已摸鱼{SYMBOLS[currency]}{_format_amount(shown, currency)}"


def accrued(settings: PaySettings, moment: datetime) -> Decimal:
    """货币单位下的今日累计，不换算、不舍入。"""
    total = _payable_seconds(settings)
    daily = _daily_pay(settings)
    if total <= 0 or daily <= 0:
        return Decimal(0)
    elapsed = min(_elapsed_payable(settings, moment), total)
    if elapsed <= 0:
        return Decimal(0)
    if elapsed >= total:
        return daily
    return daily * Decimal(elapsed) / Decimal(total)


def project(
    amount: Decimal,
    unit: str,
    display: str,
    per_eur: Optional[Mapping[str, Decimal]],
) -> tuple[Decimal, str]:
    """换成货币显示。牌价不够时退回货币单位。"""
    if display == unit or display not in CURRENCIES or unit not in CURRENCIES:
        return amount, unit if unit in CURRENCIES else "CNY"
    unit_per = _per_eur(unit, per_eur)
    display_per = _per_eur(display, per_eur)
    if unit_per is None or display_per is None:
        return amount, unit
    return amount * display_per / unit_per, display


def _daily_pay(settings: PaySettings) -> Decimal:
    if settings.pay_mode == "monthly":
        return settings.monthly_amount / MONTHLY_DAYS
    return settings.daily_amount


def _work(settings: PaySettings) -> Optional[tuple[int, int]]:
    start = settings.work_start
    end = settings.work_end
    if start is None or end is None or start >= end:
        return None
    return start, end


def _lunch(settings: PaySettings) -> Optional[tuple[int, int]]:
    work = _work(settings)
    if work is None:
        return None
    start = settings.lunch_start
    end = settings.lunch_end
    if start is None or end is None or start >= end:
        return None
    if start < work[0] or end > work[1]:
        return None
    return start, end


def _payable_seconds(settings: PaySettings) -> int:
    work = _work(settings)
    if work is None:
        return 0
    span = (work[1] - work[0]) * 60
    lunch = _lunch(settings)
    if lunch is None:
        return span
    return span - (lunch[1] - lunch[0]) * 60


def _elapsed_payable(settings: PaySettings, moment: datetime) -> int:
    work = _work(settings)
    if work is None:
        return 0
    now = _second(moment)
    start = work[0] * 60
    end = work[1] * 60
    if now <= start:
        return 0
    elapsed = min(now, end) - start
    lunch = _lunch(settings)
    if lunch is not None:
        lunch_start = lunch[0] * 60
        cut = min(now, end, lunch[1] * 60)
        if cut > lunch_start:
            elapsed -= cut - lunch_start
    return max(0, elapsed)


def _resting(settings: PaySettings, moment: datetime) -> bool:
    work = _work(settings)
    lunch = _lunch(settings)
    if work is None or lunch is None:
        return False
    now = _second(moment)
    if now < work[0] * 60 or now >= work[1] * 60:
        return False
    return lunch[0] * 60 <= now < lunch[1] * 60


def _accepted_lunch(
    work_start: int,
    work_end: int,
    start_text: str,
    end_text: str,
) -> Optional[tuple[int, int]]:
    if not start_text.strip() and not end_text.strip():
        return None
    start = parse_clock(start_text)
    end = parse_clock(end_text)
    if start is None or end is None or start >= end:
        return None
    if start < work_start or end > work_end:
        return None
    return start, end


def _per_eur(currency: str, per_eur: Optional[Mapping[str, Decimal]]) -> Optional[Decimal]:
    if currency == "EUR":
        return Decimal(1)
    if not per_eur or currency not in per_eur:
        return None
    rate = per_eur[currency]
    if rate <= 0:
        return None
    return rate


def _format_amount(amount: Decimal, currency: str) -> str:
    quantum = Decimal(1) if currency in ZERO_DECIMAL else Decimal("0.01")
    rounded = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    if currency in ZERO_DECIMAL:
        return str(int(rounded))
    return f"{rounded:.2f}"


def _second(moment: datetime) -> int:
    return moment.hour * 3600 + moment.minute * 60 + moment.second
