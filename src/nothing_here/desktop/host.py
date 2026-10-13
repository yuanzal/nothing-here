from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional, Sequence

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from nothing_here.ui.card_window import CARD_GAP, CARD_WIDTH, MARGIN_RIGHT, MARGIN_TOP

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
SMTO_NORMAL = 0x0000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
WM_SPAWN_WORKER = 0x052C
HWND_TOP = 0
HWND_TOPMOST = -1

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _as_hwnd(value: int) -> wintypes.HWND:
    return wintypes.HWND(value & 0xFFFFFFFFFFFFFFFF)


def clamp_origin(
    x: int,
    y: int,
    width: int,
    height: int,
    work_x: int,
    work_y: int,
    work_w: int,
    work_h: int,
) -> tuple[int, int]:
    max_x = work_x + max(0, work_w - width)
    max_y = work_y + max(0, work_h - height)
    return (min(max(x, work_x), max_x), min(max(y, work_y), max_y))


def _user32() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("user32", use_last_error=True)
    dll.FindWindowW.restype = wintypes.HWND
    dll.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    dll.FindWindowExW.restype = wintypes.HWND
    dll.FindWindowExW.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    dll.SendMessageTimeoutW.restype = wintypes.LPARAM
    dll.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_ulonglong),
    ]
    dll.EnumWindows.restype = wintypes.BOOL
    dll.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    dll.SetParent.restype = wintypes.HWND
    dll.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    dll.GetWindowLongPtrW.restype = ctypes.c_longlong
    dll.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    dll.SetWindowLongPtrW.restype = ctypes.c_longlong
    dll.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
    dll.SetWindowPos.restype = wintypes.BOOL
    dll.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    dll.GetForegroundWindow.restype = wintypes.HWND
    dll.GetForegroundWindow.argtypes = []
    dll.SetForegroundWindow.restype = wintypes.BOOL
    dll.SetForegroundWindow.argtypes = [wintypes.HWND]
    dll.SetFocus.restype = wintypes.HWND
    dll.SetFocus.argtypes = [wintypes.HWND]
    dll.GetWindowThreadProcessId.restype = wintypes.DWORD
    dll.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    dll.AttachThreadInput.restype = wintypes.BOOL
    dll.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    return dll


class DesktopHost:
    def __init__(self) -> None:
        self._user32 = _user32()
        self._enum_proc = None
        # Parent is the desktop window that owns the icons, not the WorkerW
        # behind them. A window behind the icons never receives the mouse.
        self._desktop = self._find_icon_host()
        self.floating = False

    @property
    def available(self) -> bool:
        return bool(self._desktop)

    def work_rect(self) -> QRect:
        screen = QApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        return screen.availableGeometry()

    def attach(self, widget: QWidget) -> bool:
        return self.prepare(widget, self.floating)

    def prepare(self, widget: QWidget, floating: bool) -> bool:
        hwnd = wintypes.HWND(int(widget.winId()))
        if floating:
            # A window that has already been parented to the desktop will not
            # accept HWND_TOPMOST. Callers recreate the card before this.
            self.floating = True
            self._stack(hwnd, HWND_TOPMOST)
        else:
            if not self._desktop:
                return False
            self.floating = False
            self._user32.SetParent(hwnd, wintypes.HWND(self._desktop))
            self._stack(hwnd, HWND_TOP)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.set_click_through(widget, False)
        widget.update()
        return True

    def set_click_through(self, widget: QWidget, enabled: bool) -> None:
        # The card itself must keep receiving the mouse, otherwise it cannot be dragged.
        # Clicks outside the card still hit the desktop, because the window is only card-sized.
        del enabled
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        hwnd = wintypes.HWND(int(widget.winId()))
        ex = self._user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_TRANSPARENT:
            self._user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex & ~WS_EX_TRANSPARENT)
            self._stack(hwnd, self._insert_after())

    def focus_widget(self, widget: QWidget) -> None:
        """Try to give a desktop-embedded card real keyboard focus (WorkerW normally steals it)."""
        hwnd = wintypes.HWND(int(widget.winId()))
        foreground = self._user32.GetForegroundWindow()
        if foreground == hwnd:
            self._user32.SetFocus(hwnd)
            return
        pid = wintypes.DWORD()
        tid_fore = self._user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
        tid_self = self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if tid_fore and tid_self and tid_fore != tid_self:
            self._user32.AttachThreadInput(tid_fore, tid_self, True)
            self._user32.SetForegroundWindow(hwnd)
            self._user32.SetFocus(hwnd)
            self._user32.AttachThreadInput(tid_fore, tid_self, False)
        else:
            self._user32.SetForegroundWindow(hwnd)
            self._user32.SetFocus(hwnd)

    def place(
        self,
        widgets: Sequence[QWidget],
        min_front_height: int,
        origins: Sequence[Optional[tuple[int, int]]],
    ) -> list[tuple[int, int]]:
        work = self.work_rect()
        placed: list[tuple[int, int]] = []
        y = work.top() + MARGIN_TOP
        count = len(widgets)
        for index, widget in enumerate(widgets):
            preferred = widget.preferred_height()  # type: ignore[attr-defined]
            saved = origins[index] if index < len(origins) else None
            if saved is None:
                remaining = count - index - 1
                reserved = remaining * (min_front_height + CARD_GAP)
                max_height = work.top() + work.height() - y - reserved
                height = max(1, min(preferred, max_height))
                x = work.left() + work.width() - MARGIN_RIGHT - CARD_WIDTH
                origin = (x, y)
                y += height + CARD_GAP
            else:
                max_height = work.height()
                height = max(1, min(preferred, max_height))
                origin = saved
            origin = self.move(widget, origin[0], origin[1], height)
            placed.append(origin)
        return placed

    def move(self, widget: QWidget, x: int, y: int, height: Optional[int] = None) -> tuple[int, int]:
        work = self.work_rect()
        preferred = widget.preferred_height()  # type: ignore[attr-defined]
        if height is None:
            height = min(preferred, work.height())
        height = max(1, min(preferred, height, work.height()))
        x, y = clamp_origin(x, y, CARD_WIDTH, height, work.left(), work.top(), work.width(), work.height())
        self._commit_geometry(widget, x, y, CARD_WIDTH, height)
        widget.set_screen_origin(x, y)  # type: ignore[attr-defined]
        return (x, y)

    def _commit_geometry(self, widget: QWidget, x: int, y: int, width: int, height: int) -> None:
        # Qt geometry is in logical pixels. SetWindowPos wants physical pixels.
        ratio = widget.devicePixelRatioF()
        widget.setGeometry(x, y, width, height)
        hwnd = wintypes.HWND(int(widget.winId()))
        self._user32.SetWindowPos(
            hwnd,
            self._insert_after(),
            int(round(x * ratio)),
            int(round(y * ratio)),
            int(round(width * ratio)),
            int(round(height * ratio)),
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _insert_after(self) -> wintypes.HWND:
        return _as_hwnd(HWND_TOPMOST if self.floating else HWND_TOP)

    def _stack(self, hwnd: wintypes.HWND, insert_after: int) -> None:
        self._user32.SetWindowPos(
            hwnd,
            _as_hwnd(insert_after),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )

    def _find_icon_host(self) -> int:
        user32 = self._user32
        progman = user32.FindWindowW("Progman", None)
        if not progman:
            return 0
        found = ctypes.c_void_p(0)

        @WNDENUMPROC
        def enum_proc(hwnd: int, _lparam: int) -> bool:
            shell = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if shell:
                found.value = hwnd
            return True

        self._enum_proc = enum_proc
        result = ctypes.c_ulonglong()
        for wparam, lparam in ((0, 0), (0xD, 0x1)):
            user32.SendMessageTimeoutW(
                progman,
                WM_SPAWN_WORKER,
                wparam,
                lparam,
                SMTO_NORMAL,
                1000,
                ctypes.byref(result),
            )
            found.value = 0
            user32.EnumWindows(enum_proc, 0)
            if found.value:
                return int(found.value)
        return 0
