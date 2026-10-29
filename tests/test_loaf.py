from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from nothing_here.domain.loaf import (
    PaySettings,
    buyable,
    commit_work_times,
    days_until_payday,
    month_accrued,
    month_remaining,
    needs_rates,
    parse_amount,
    parse_clock,
    parse_good,
    parse_payday,
    seconds_until_off,
    shift_phase,
    strip_text,
    work_progress,
)
from nothing_here.paths import ui_text
from nothing_here.ui.skins import skin_for
from nothing_here.fx import parse_eur_rates, parse_vnd_rate
from nothing_here.storage.db import LoafRecord, Store


def _pay(**kwargs: object) -> PaySettings:
    base = dict(
        pay_mode="daily",
        daily_amount=Decimal("100"),
        monthly_amount=Decimal("2175"),
        unit="CNY",
        display="CNY",
        work_start=9 * 60,
        work_end=18 * 60,
        lunch_start=None,
        lunch_end=None,
    )
    base.update(kwargs)
    return PaySettings(**base)  # type: ignore[arg-type]


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 16, hour, minute, second)


class AccrualTests(unittest.TestCase):
    def test_unset_work_or_pay_stays_zero(self) -> None:
        unpaid = _pay(daily_amount=Decimal(0))
        self.assertEqual(strip_text(unpaid, _at(12, 0)), "你已摸鱼 CNY￥0.00")
        untimed = _pay(work_start=None, work_end=None)
        self.assertEqual(strip_text(untimed, _at(12, 0)), "你已摸鱼 CNY￥0.00")
        self.assertEqual(strip_text(_pay(), _at(8, 59, 59)), "你已摸鱼 CNY￥0.00")

    def test_midday_and_after_work_without_lunch(self) -> None:
        # 09:00–18:00，11:00 走过 2/9
        self.assertEqual(strip_text(_pay(), _at(11, 0)), "你已摸鱼 CNY￥22.22")
        self.assertEqual(strip_text(_pay(), _at(18, 0)), "你已摸鱼 CNY￥100.00")
        self.assertEqual(strip_text(_pay(), _at(20, 0)), "你已摸鱼 CNY￥100.00")

    def test_lunch_is_excluded_and_shows_rest(self) -> None:
        settings = _pay(lunch_start=12 * 60, lunch_end=13 * 60)
        self.assertEqual(strip_text(settings, _at(12, 30)), "休息中")
        # 可计 8 小时，13:00 已计上午 3 小时
        self.assertEqual(strip_text(settings, _at(13, 0)), "你已摸鱼 CNY￥37.50")
        self.assertEqual(strip_text(settings, _at(18, 0)), "你已摸鱼 CNY￥100.00")

    def test_lunch_may_touch_the_shift_edge_but_not_replace_it(self) -> None:
        edge = _pay(lunch_start=9 * 60, lunch_end=10 * 60)
        self.assertEqual(strip_text(edge, _at(9, 30)), "休息中")
        self.assertEqual(strip_text(edge, _at(8, 0)), "你已摸鱼 CNY￥0.00")
        full = _pay(lunch_start=9 * 60, lunch_end=18 * 60)
        self.assertEqual(strip_text(full, _at(12, 0)), "休息中")
        self.assertEqual(strip_text(full, _at(18, 0)), "你已摸鱼 CNY￥0.00")

    def test_monthly_uses_21_75_and_recomputes_from_the_new_rate(self) -> None:
        monthly = _pay(pay_mode="monthly", monthly_amount=Decimal("2175"), daily_amount=Decimal("1"))
        self.assertEqual(strip_text(monthly, _at(18, 0)), "你已摸鱼 CNY￥100.00")
        raised = _pay(daily_amount=Decimal("200"))
        self.assertEqual(strip_text(raised, _at(18, 0)), "你已摸鱼 CNY￥200.00")

    def test_currency_conversion_rounds_half_up_and_falls_back(self) -> None:
        rates = {"CNY": Decimal("7.5"), "USD": Decimal("1.5"), "JPY": Decimal("150"), "KRW": Decimal("1500"), "SGD": Decimal("1.5")}
        usd = _pay(display="USD")
        # 100 CNY = 100/7.5 EUR = 20 USD
        self.assertEqual(strip_text(usd, _at(18, 0), rates), "你已摸鱼 USD$20.00")
        yen = _pay(unit="JPY", display="JPY", daily_amount=Decimal("100"))
        self.assertEqual(strip_text(yen, _at(11, 0)), "你已摸鱼 JPY円22")
        half = _pay(unit="JPY", display="JPY", daily_amount=Decimal("9"))
        # 09:00–18:00 的一半是 13:30，4.5 日元四舍五入到 5。2/9*9 = 2
        self.assertEqual(strip_text(half, _at(13, 30)), "你已摸鱼 JPY円5")
        self.assertEqual(strip_text(usd, _at(18, 0), None), "你已摸鱼 CNY￥100.00")
        self.assertEqual(strip_text(usd, _at(18, 0), {"USD": Decimal("1.5")}), "你已摸鱼 CNY￥100.00")
        dong = _pay(display="VND")
        self.assertEqual(strip_text(dong, _at(18, 0), rates), "你已摸鱼 CNY￥100.00")
        self.assertTrue(needs_rates("CNY", "VND", rates))
        dong_rates = {**rates, "VND": Decimal("26000")}
        self.assertFalse(needs_rates("CNY", "VND", dong_rates))
        # 100 CNY = 100/7.5 EUR × 26000 = 346666.6… → ₫346667
        self.assertEqual(strip_text(dong, _at(18, 0), dong_rates), "你已摸鱼 VND₫346667")
        native = _pay(unit="VND", display="VND", daily_amount=Decimal("25834000"))
        self.assertEqual(strip_text(native, _at(11, 0)), "你已摸鱼 VND₫5740889")

    def test_clock_and_amount_parsing(self) -> None:
        self.assertEqual(parse_clock("09:00"), 9 * 60)
        self.assertEqual(parse_clock("9:00"), 9 * 60)
        self.assertIsNone(parse_clock("24:00"))
        self.assertIsNone(parse_clock("9:0"))
        self.assertEqual(parse_amount("10.5", "CNY"), Decimal("10.5"))
        self.assertIsNone(parse_amount("10.555", "CNY"))
        self.assertIsNone(parse_amount("-1", "CNY"))
        self.assertIsNone(parse_amount("10.5", "JPY"))
        self.assertEqual(parse_amount("10", "JPY"), Decimal(10))
        self.assertEqual(parse_amount("25834000", "VND"), Decimal("25834000"))
        self.assertIsNone(parse_amount("1.2", "VND"))


class PaydayTests(unittest.TestCase):
    def test_short_month_falls_on_last_day_and_today_is_zero(self) -> None:
        self.assertEqual(parse_payday("10"), 10)
        self.assertIsNone(parse_payday(""))
        self.assertIsNone(parse_payday("32"))
        # 2026-10-22，发薪日 10 → 11 月 10 日，19 天
        oct22 = datetime(2026, 10, 22, 12, 0)
        self.assertEqual(days_until_payday(oct22, 10), 19)
        self.assertEqual(days_until_payday(oct22, 22), 0)
        feb = datetime(2026, 2, 10, 12, 0)
        self.assertEqual(days_until_payday(feb, 31), 18)
        self.assertEqual(days_until_payday(datetime(2026, 2, 28, 9, 0), 31), 0)


class BoardMathTests(unittest.TestCase):
    def test_month_accrued_ignores_today_close_and_does_not_backfill(self) -> None:
        moment = datetime(2026, 10, 22, 11, 0)
        closes = {"2026-10-01": Decimal("100"), "2026-10-22": Decimal("1")}
        today = Decimal(100) * Decimal(2) / Decimal(9)
        self.assertEqual(month_accrued(_pay(), moment, closes), Decimal(100) + today)
        self.assertEqual(month_accrued(_pay(), moment, {}), today)

    def test_month_remaining_is_unfinished_today_plus_later_calendar_days(self) -> None:
        today = Decimal(100) * Decimal(2) / Decimal(9)
        left = month_remaining(_pay(), datetime(2026, 10, 22, 11, 0))
        self.assertEqual(left, Decimal(100) - today + Decimal(900))

    def test_countdown_runs_through_lunch_and_progress_freezes(self) -> None:
        settings = _pay(lunch_start=12 * 60, lunch_end=13 * 60)
        self.assertEqual(shift_phase(settings, _at(12, 30)), "lunch")
        self.assertEqual(seconds_until_off(settings, _at(12, 30)), 5 * 3600 + 30 * 60)
        lunch = work_progress(settings, _at(12, 30))
        self.assertEqual(lunch, work_progress(settings, _at(13, 0)))
        self.assertEqual(shift_phase(settings, _at(18, 0)), "after")
        self.assertEqual(seconds_until_off(settings, _at(20, 0)), 0)

    def test_good_price_must_be_positive(self) -> None:
        self.assertIsNone(parse_good("x", "咖啡", "0", "杯", "CNY", True))
        self.assertIsNone(parse_good("x", "咖啡", "-1", "杯", "CNY", True))
        item = parse_good("x", "咖啡", "25", "杯", "CNY", True)
        assert item is not None
        self.assertEqual(buyable(Decimal("347.66"), item.price), Decimal("13.9064"))


class WorkCommitTests(unittest.TestCase):
    def test_invalid_shift_keeps_the_dialog_open(self) -> None:
        rejected = commit_work_times("18:00", "09:00", "", "")
        self.assertFalse(rejected.ok)
        self.assertFalse(commit_work_times("九点", "18:00", "", "").ok)

    def test_bad_lunch_is_stored_as_unset(self) -> None:
        saved = commit_work_times("09:00", "18:00", "12:00", "19:00")
        self.assertTrue(saved.ok)
        self.assertEqual((saved.work_start, saved.work_end), (9 * 60, 18 * 60))
        self.assertIsNone(saved.lunch_start)
        self.assertIsNone(saved.lunch_end)
        half = commit_work_times("09:00", "18:00", "12:00", "")
        self.assertIsNone(half.lunch_start)
        empty = commit_work_times("09:00", "18:00", "  ", "")
        self.assertIsNone(empty.lunch_start)
        ok = commit_work_times("09:00", "18:00", "12:00", "13:00")
        self.assertEqual((ok.lunch_start, ok.lunch_end), (12 * 60, 13 * 60))


class LoafStoreTests(unittest.TestCase):
    def test_loaf_and_rate_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "study.db")
            fresh = store.load_loaf()
            self.assertEqual(fresh.pay_mode, "daily")
            self.assertEqual(fresh.unit, "CNY")
            self.assertFalse(fresh.hidden)
            store.save_loaf(
                LoafRecord(
                    hidden=True,
                    pay_mode="monthly",
                    daily_amount="12.50",
                    monthly_amount="8000",
                    unit="USD",
                    display="EUR",
                    work_start=9 * 60,
                    work_end=18 * 60,
                    lunch_start=12 * 60,
                    lunch_end=13 * 60,
                    origin=(3, 4),
                )
            )
            store.save_fx("2026-10-16", {"USD": "1.1", "CNY": "7.5"})
            store.close()
            again = Store(Path(folder) / "study.db")
            loaf = again.load_loaf()
            self.assertTrue(loaf.hidden)
            self.assertEqual(loaf.pay_mode, "monthly")
            self.assertEqual(loaf.daily_amount, "12.50")
            self.assertEqual(loaf.display, "EUR")
            self.assertEqual(loaf.origin, (3, 4))
            self.assertIsNone(loaf.payday)
            self.assertEqual(again.load_fx(), ("2026-10-16", {"USD": "1.1", "CNY": "7.5"}))
            again.save_fx("2026-10-17", None)
            self.assertEqual(again.load_fx(), ("2026-10-17", {"USD": "1.1", "CNY": "7.5"}))
            again.close()

    def test_payday_goods_and_day_closes_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "study.db")
            goods = store.load_goods()
            self.assertEqual(goods[0].name, "咖啡")
            self.assertTrue(goods[0].shown)
            store.save_loaf(LoafRecord(payday=31, daily_amount="0", monthly_amount="0"))
            store.save_day_close("2026-10-01", Decimal("100"))
            store.close()
            again = Store(Path(folder) / "study.db")
            self.assertEqual(again.load_loaf().payday, 31)
            self.assertEqual(again.load_day_closes()["2026-10-01"], Decimal("100"))
            again.clear_day_closes()
            self.assertEqual(again.load_day_closes(), {})
            self.assertEqual(len(again.load_goods()), 3)
            again.close()


class RateParseTests(unittest.TestCase):
    def test_requires_all_five_quotes(self) -> None:
        payload = (
            b'[{"quote":"USD","rate":1.1},{"quote":"CNY","rate":7.2},'
            b'{"quote":"JPY","rate":160},{"quote":"KRW","rate":1400},'
            b'{"quote":"SGD","rate":1.4}]'
        )
        parsed = parse_eur_rates(payload)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["JPY"], Decimal(160))
        self.assertIsNone(parse_eur_rates(b'[{"quote":"USD","rate":1.1}]'))
        self.assertIsNone(parse_eur_rates(b"[]"))

    def test_vnd_rate_from_pair_payload(self) -> None:
        self.assertEqual(parse_vnd_rate(b'{"rate":29007.5}'), Decimal("29007.5"))
        self.assertEqual(
            parse_vnd_rate(b'{"rates":{"VND":29007}}'),
            Decimal("29007"),
        )
        self.assertIsNone(parse_vnd_rate(b'{"rate":0}'))
        self.assertIsNone(parse_vnd_rate(b"[]"))


class SkinTests(unittest.TestCase):
    def test_plain_is_the_only_skin_and_unknown_ids_fall_back(self) -> None:
        plain = skin_for("plain")
        self.assertEqual(plain.label, "极简无痕")
        self.assertEqual([mode.mode_id for mode in plain.color_modes], ["light", "dark", "custom"])
        self.assertIs(skin_for("cute"), plain)
        self.assertLessEqual(plain.strip_metrics.pad_x, 12)
        self.assertEqual(plain.strip_metrics.min_width, 1)

    def test_loaf_board_html_is_bundled_with_ui_assets(self) -> None:
        page = ui_text("loaf_board.html")
        self.assertIn("摸鱼看板", page)
        self.assertIn("<!DOCTYPE html>", page)


if __name__ == "__main__":
    unittest.main()
