"""向 Frankfurter 取日牌价。欧洲央行五种失败时返回 None，由调用方用缓存。"""

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
_VND_URL = "https://api.frankfurter.dev/v2/rate/eur/vnd"
_QUOTES = frozenset({"USD", "CNY", "JPY", "KRW", "SGD"})


def fetch_eur_rates(timeout: float = 8) -> Optional[dict[str, Decimal]]:
    """除欧元外相对 1 欧元的牌价。欧洲央行五种缺一即失败；越南盾另取，没有也不挡其余。"""
    request = Request(_URL, headers={"User-Agent": "NothingHere"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    rates = parse_eur_rates(payload)
    if rates is None:
        return None
    vnd = _fetch_vnd_rate(timeout)
    if vnd is not None:
        rates["VND"] = vnd
    return rates


def _fetch_vnd_rate(timeout: float) -> Optional[Decimal]:
    request = Request(_VND_URL, headers={"User-Agent": "NothingHere"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    return parse_vnd_rate(payload)


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


def parse_vnd_rate(payload: bytes) -> Optional[Decimal]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    raw = None
    if isinstance(data, dict):
        raw = data.get("rate")
        quotes = data.get("rates")
        if raw is None and isinstance(quotes, dict):
            raw = quotes.get("VND")
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("quote") == "VND":
                raw = row.get("rate")
                break
    try:
        rate = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if rate <= 0:
        return None
    return rate
