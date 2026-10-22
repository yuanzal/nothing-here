"""设置你的工作状态：收入方式、两个金额、货币单位和四个时刻，一个窗口。

时刻用时间控件：可以直接键入「时:分」，也可以点上下箭头或滚轮选。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTime
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from nothing_here.domain.loaf import (
    CURRENCY_LABELS,
    WorkCommit,
    commit_work_times,
    parse_amount,
    parse_clock,
)


def _time_edit(minutes: int | None, fallback: QTime) -> QDateTimeEdit:
    edit = QDateTimeEdit()
    edit.setDisplayFormat("HH:mm")
    edit.setTimeSpec(Qt.TimeSpec.LocalTime)
    edit.setButtonSymbols(edit.buttonSymbols())  # keep up/down arrows visible
    if minutes is None:
        edit.setTime(fallback)
    else:
        edit.setTime(QTime(minutes // 60, minutes % 60))
    return edit


def _minutes(edit: QDateTimeEdit) -> str:
    return edit.time().toString("HH:mm")


class WorkStatusDialog(QDialog):
    def __init__(
        self,
        pay_mode: str,
        daily_amount: str,
        monthly_amount: str,
        unit: str,
        start: str,
        end: str,
        lunch_start: str,
        lunch_end: str,
    ) -> None:
        super().__init__()
        self.setWindowTitle("设置你的工作状态")
        self._mode = QComboBox()
        self._mode.addItem("按日薪", "daily")
        self._mode.addItem("按月薪", "monthly")
        mode_index = self._mode.findData("monthly" if pay_mode == "monthly" else "daily")
        self._mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self._daily = QLineEdit(daily_amount)
        self._monthly = QLineEdit(monthly_amount)
        self._unit = QComboBox()
        for code, label in CURRENCY_LABELS:
            self._unit.addItem(label, code)
        unit_index = self._unit.findData(unit)
        self._unit.setCurrentIndex(unit_index if unit_index >= 0 else 0)
        nine = QTime(9, 0)
        self._start = _time_edit(_parse_text(start), nine)
        self._end = _time_edit(_parse_text(end), QTime(18, 0))
        self._lunch_on = QCheckBox("有午休")
        self._lunch_on.setChecked(lunch_start.strip() != "" or lunch_end.strip() != "")
        self._lunch_start = _time_edit(_parse_text(lunch_start), nine)
        self._lunch_end = _time_edit(_parse_text(lunch_end), QTime(13, 0))
        for edit in (self._lunch_start, self._lunch_end):
            edit.setEnabled(self._lunch_on.isChecked())
        self._lunch_on.toggled.connect(self._toggle_lunch)
        form = QFormLayout()
        form.addRow("收入方式", self._mode)
        form.addRow("日薪", self._daily)
        form.addRow("月薪", self._monthly)
        form.addRow("货币单位", self._unit)
        form.addRow("上班起始", self._start)
        form.addRow("下班终止", self._end)
        form.addRow(self._lunch_on, self._lunch_start)
        form.addRow("", self._lunch_end)
        self._hint = QLabel("时刻可以直接键入，或用上下箭头选。没勾中的那种金额照旧存着。")
        self._hint.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._hint)
        layout.addWidget(buttons)

    def pay_mode(self) -> str:
        return str(self._mode.currentData() or "daily")

    def daily_amount(self) -> str:
        return self._daily_amount

    def monthly_amount(self) -> str:
        return self._monthly_amount

    def unit(self) -> str:
        return self._unit_value

    def commit(self) -> WorkCommit:
        return self._commit

    def _toggle_lunch(self, on: bool) -> None:
        self._lunch_start.setEnabled(on)
        self._lunch_end.setEnabled(on)

    def _try_accept(self) -> None:
        unit = str(self._unit.currentData() or "")
        daily = parse_amount(self._daily.text(), unit)
        monthly = parse_amount(self._monthly.text(), unit)
        if daily is None or monthly is None:
            self._hint.setText("金额无效。写成非负数字，日元、韩元和越南盾取整数，其余到分。")
            return
        lunch_start = _minutes(self._lunch_start) if self._lunch_on.isChecked() else ""
        lunch_end = _minutes(self._lunch_end) if self._lunch_on.isChecked() else ""
        result = commit_work_times(
            _minutes(self._start),
            _minutes(self._end),
            lunch_start,
            lunch_end,
        )
        if not result.ok:
            self._hint.setText("上班起始要早于下班终止。")
            return
        self._daily_amount = format(daily, "f")
        self._monthly_amount = format(monthly, "f")
        self._unit_value = unit
        self._commit = result
        self.accept()


def _parse_text(text: str) -> int | None:
    return parse_clock(text)
