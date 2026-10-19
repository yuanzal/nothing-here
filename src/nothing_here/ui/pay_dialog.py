"""设置日薪或月薪时，同时选定货币单位。"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from nothing_here.domain.loaf import CURRENCY_LABELS, ZERO_DECIMAL, parse_amount


class PayAmountDialog(QDialog):
    def __init__(self, title: str, amount: str, unit: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self._title = title
        self._amount_value = amount
        self._unit_value = unit
        self._amount = QLineEdit(amount)
        self._unit = QComboBox()
        for code, label in CURRENCY_LABELS:
            self._unit.addItem(label, code)
        index = self._unit.findData(unit)
        self._unit.setCurrentIndex(index if index >= 0 else 0)
        self._unit.currentIndexChanged.connect(lambda _index: self._refresh_hint())
        form = QFormLayout()
        form.addRow("金额", self._amount)
        form.addRow("货币单位", self._unit)
        self._hint = QLabel("")
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
        self._refresh_hint()

    def amount(self) -> str:
        return self._amount_value

    def unit(self) -> str:
        return self._unit_value

    def _refresh_hint(self) -> None:
        code = str(self._unit.currentData() or "CNY")
        precision = "整数" if code in ZERO_DECIMAL else "精确到分"
        self._hint.setText(f"{self._title}按{precision}填写。货币单位日薪和月薪共用，不改另一个金额的数字。")

    def _try_accept(self) -> None:
        code = str(self._unit.currentData() or "")
        amount = parse_amount(self._amount.text(), code)
        if amount is None:
            self._hint.setText("金额无效。")
            return
        self._amount_value = format(amount, "f")
        self._unit_value = code
        self.accept()
