"""摸鱼看板：应用内 HTML 窗。不是卡片，也不贴壁纸层。"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional

from PyQt6.QtCore import QObject, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent, QShowEvent
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from nothing_here.domain.loaf import (
    CURRENCY_LABELS,
    Good,
    PaySettings,
    accrued,
    buyable,
    daily_pay,
    days_until_payday,
    format_clock,
    minutes_for_price,
    money_label,
    month_accrued,
    month_days,
    month_elapsed_days,
    month_remaining,
    per_minute,
    per_second,
    seconds_until_off,
    shift_phase,
    shown_good,
    work_hours,
    work_progress,
)

_HTML = Path(__file__).with_name("loaf_board.html")


class BoardBridge(QObject):
    snapshot = pyqtSignal(str)
    pay_saved = pyqtSignal(str)
    goods_saved = pyqtSignal(str)
    clear_asked = pyqtSignal()
    page_ready = pyqtSignal()

    @pyqtSlot(str)
    def save_pay(self, raw: str) -> None:
        self.pay_saved.emit(raw)

    @pyqtSlot(str)
    def save_goods(self, raw: str) -> None:
        self.goods_saved.emit(raw)

    @pyqtSlot()
    def ask_clear(self) -> None:
        self.clear_asked.emit()

    @pyqtSlot()
    def ready(self) -> None:
        self.page_ready.emit()


class LoafBoard(QMainWindow):
    closed = pyqtSignal()
    moved_to = pyqtSignal(int, int, int, int)
    pay_saved = pyqtSignal(str)
    goods_saved = pyqtSignal(str)
    clear_asked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("摸鱼看板")
        self.setMinimumSize(960, 720)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(1100, 860)
        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)
        self._bridge = BoardBridge()
        self._bridge.pay_saved.connect(self.pay_saved)
        self._bridge.goods_saved.connect(self.goods_saved)
        self._bridge.clear_asked.connect(self.clear_asked)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._pending: Optional[str] = None
        self._ready = False
        self._bridge.page_ready.connect(self._on_ready)
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        script = QWebEngineScript()
        script.setName("qwebchannel")
        script.setSourceUrl(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(script)
        self._view.load(QUrl.fromLocalFile(str(_HTML.resolve())))

    def push(self, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        self._pending = raw
        if self._ready:
            self._bridge.snapshot.emit(raw)

    def _on_ready(self) -> None:
        self._ready = True
        if self._pending is not None:
            self._bridge.snapshot.emit(self._pending)

    def confirm_clear(self) -> bool:
        answer = QMessageBox.question(
            self,
            "清除摸鱼记录",
            "只删除已冻住的日结，工作状态和实物不动。不能撤销。",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def closeEvent(self, event: QCloseEvent) -> None:
        self._emit_geometry()
        self.closed.emit()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._emit_geometry()

    def moveEvent(self, event) -> None:  # type: ignore[override]
        super().moveEvent(event)
        if self.isVisible():
            self._emit_geometry()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.isVisible():
            self._emit_geometry()

    def _emit_geometry(self) -> None:
        geo = self.geometry()
        self.moved_to.emit(geo.x(), geo.y(), geo.width(), geo.height())


def board_theme(preset: str, text_color: Optional[str], button_preset: str) -> dict[str, str]:
    dark = preset == "dark" or (preset == "custom" and button_preset == "dark")
    fg = "#F5F5F5" if dark else "#1C1C1C"
    if preset == "custom" and text_color:
        fg = text_color
    if dark:
        return {
            "bg": "#111111",
            "fg": fg,
            "muted": "#A3A3A3",
            "card": "#1C1C1C",
            "line": "#2A2A2A",
        }
    return {
        "bg": "#FFFFFF",
        "fg": fg,
        "muted": "#666666",
        "card": "#F4F4F6",
        "line": "#E4E4E8",
    }


def board_payload(
    settings: PaySettings,
    moment: datetime,
    goods: tuple[Good, ...],
    closes: Mapping[str, Decimal],
    theme: dict[str, str],
    per_eur: Optional[Mapping[str, Decimal]] = None,
) -> dict:
    unit_today = accrued(settings, moment)
    daily = daily_pay(settings)
    left = daily - unit_today
    if left < 0:
        left = Decimal(0)
    seconds = seconds_until_off(settings, moment)
    phase = shift_phase(settings, moment)
    progress = work_progress(settings, moment)
    payday_in = days_until_payday(moment, settings.payday)
    item = shown_good(goods)
    good = None
    if item is not None:
        count = buyable(unit_today, item.price)
        whole = int(count)
        frac = count - Decimal(whole)
        minutes = minutes_for_price(settings, item.price)
        good = {
            "name": item.name,
            "price": f"{money_label(item.price, settings.unit, settings.unit)} / {item.unit_label}",
            "buyable": _plain(count),
            "unit_label": item.unit_label,
            "frac": float(frac),
            "hint": f"已计 {whole} {item.unit_label} · 再计一份约 {_plain(minutes)} 分钟",
        }
    form = {
        "pay_mode": settings.pay_mode if settings.pay_mode in ("daily", "monthly") else "daily",
        "daily": format(settings.daily_amount, "f"),
        "monthly": format(settings.monthly_amount, "f"),
        "unit": settings.unit,
        "units": [list(pair) for pair in CURRENCY_LABELS],
        "work_start": _clock(settings.work_start),
        "work_end": _clock(settings.work_end),
        "lunch_start": _clock(settings.lunch_start),
        "lunch_end": _clock(settings.lunch_end),
        "payday": "" if settings.payday is None else str(settings.payday),
    }
    return {
        "theme": theme,
        "clock": {"h": seconds // 3600, "m": (seconds % 3600) // 60, "s": seconds % 60},
        "progress": float(progress),
        "phase_text": _phase_text(phase, progress),
        "countdown_label": _countdown_label(phase),
        "today": money_label(unit_today, settings.unit, settings.display, per_eur),
        "left_today": money_label(left, settings.unit, settings.display, per_eur),
        "full_today": money_label(daily, settings.unit, settings.display, per_eur),
        "per_min": money_label(per_minute(settings), settings.unit, settings.display, per_eur),
        "per_sec": money_label(per_second(settings), settings.unit, settings.display, per_eur),
        "payday_in": "—" if payday_in is None else str(payday_in),
        "payday_sub": "" if payday_in is None else ("今天发薪" if payday_in == 0 else "天"),
        "month_days": str(month_days(moment)),
        "elapsed": f"已过 { _plain(month_elapsed_days(settings, moment)) } 天",
        "month_acc": money_label(
            month_accrued(settings, moment, closes), settings.unit, settings.display, per_eur
        ),
        "month_left": money_label(
            month_remaining(settings, moment), settings.unit, settings.display, per_eur
        ),
        "hours": f"{_plain(work_hours(settings))} 小时",
        "good": good,
        "form": form,
        "goods": [
            {
                "key": g.key,
                "name": g.name,
                "price": format(g.price, "f"),
                "unit_label": g.unit_label,
                "shown": g.shown,
            }
            for g in goods
        ],
    }


def _phase_text(phase: str, progress: Decimal) -> str:
    pct = f"{int(progress * 100)}%"
    if phase == "lunch":
        return f"休息中 · 今日进度 {pct}"
    if phase == "after":
        return "已下班"
    if phase == "before":
        return "还未上班"
    if phase == "idle":
        return "还没设工作时段"
    return f"今日进度 {pct}"


def _countdown_label(phase: str) -> str:
    if phase == "after":
        return "今天已经下班"
    if phase == "idle":
        return "还没设下班时间"
    return "距离今天下班还有"


def _clock(minute: Optional[int]) -> str:
    if minute is None:
        return ""
    return format_clock(minute)


def _plain(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
