"""向 Frankfurter 取欧洲央行日牌价。失败时返回 None，由调用方用缓存。"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

_URL = (
    "https://api.frankfurter.dev/v2/rates"
    "?base=EUR&quotes=USD,CNY,JPY,KRW,SGD&providers=ecb"
)
_QUOTES = frozenset({"USD", "CNY", "JPY", "KRW", "SGD"})


def fetch_eur_rates(timeout: float = 8) -> Optional[dict[str, Decimal]]:
    """六种货币里除欧元外，每种相对 1 欧元的牌价。缺任何一种都算失败。"""
    request = Request(_URL, headers={"User-Agent": "NothingHere"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    return parse_eur_rates(payload)


def parse_eur_rates(payload: bytes) -> Optional[dict[str, Decimal]]:
    try:
        rows = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(rows, list):
        return None
    rates: dict[str, Decimal] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        quote = row.get("quote")
        raw = row.get("rate")
        if not isinstance(quote, str) or quote not in _QUOTES:
            continue
        try:
            rate = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            continue
        if rate <= 0:
            continue
        rates[quote] = rate
    if set(rates) != _QUOTES:
        return None
    return rates
