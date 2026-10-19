"""一次填写上班和午休的四个时刻。"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from nothing_here.domain.loaf import WorkCommit, commit_work_times


class WorkSpanDialog(QDialog):
    def __init__(
        self,
        start: str,
        end: str,
        lunch_start: str,
        lunch_end: str,
    ) -> None:
        super().__init__()
        self.setWindowTitle("设置工作时长")
        self._commit = WorkCommit(False)
        self._start = QLineEdit(start)
        self._end = QLineEdit(end)
        self._lunch_start = QLineEdit(lunch_start)
        self._lunch_end = QLineEdit(lunch_end)
        form = QFormLayout()
        form.addRow("上班起始", self._start)
        form.addRow("下班终止", self._end)
        form.addRow("午休起始", self._lunch_start)
        form.addRow("午休终止", self._lunch_end)
        self._hint = QLabel("时刻写成 09:00。午休可以留空。")
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

    def commit(self) -> WorkCommit:
        return self._commit

    def _try_accept(self) -> None:
        result = commit_work_times(
            self._start.text(),
            self._end.text(),
            self._lunch_start.text(),
            self._lunch_end.text(),
        )
        if not result.ok:
            self._hint.setText("上班起始要早于下班终止，并且写成 时:分。")
            return
        self._commit = result
        self.accept()
