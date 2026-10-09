from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Sequence

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QWidget

from nothing_here.ui.card_window import CARD_GAP, CARD_WIDTH, MARGIN_RIGHT, MARGIN_TOP

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
SMTO_NORMAL = 0x0000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
WM_SPAWN_WORKER = 0x052C

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


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
    return dll


class DesktopHost:
    def __init__(self) -> None:
        self._user32 = _user32()
        self._enum_proc = None
        self._worker = self._find_workerw()

    @property
    def available(self) -> bool:
        return bool(self._worker)

    def work_rect(self) -> QRect:
        screen = QApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        return screen.availableGeometry()

    def attach(self, widget: QWidget) -> bool:
        if not self._worker:
            return False
        hwnd = wintypes.HWND(int(widget.winId()))
        self._user32.SetParent(hwnd, wintypes.HWND(self._worker))
        style = self._user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
        style = (style | WS_CHILD) & ~WS_POPUP
        self._user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        ex = self._user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        self._user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        self._user32.SetWindowPos(
            hwnd,
            wintypes.HWND(0),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        return True

    def set_click_through(self, widget: QWidget, enabled: bool) -> None:
        from PyQt6.QtCore import Qt

        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        hwnd = wintypes.HWND(int(widget.winId()))
        ex = self._user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if enabled:
            ex |= WS_EX_TRANSPARENT
        else:
            ex &= ~WS_EX_TRANSPARENT
        self._user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        self._user32.SetWindowPos(
            hwnd,
            wintypes.HWND(0),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

    def place(self, widgets: Sequence[QWidget], min_front_height: int) -> None:
        work = self.work_rect()
        x = work.right() - MARGIN_RIGHT - CARD_WIDTH
        y = work.top() + MARGIN_TOP
        count = len(widgets)
        for index, widget in enumerate(widgets):
            remaining = count - index - 1
            reserved = remaining * (min_front_height + CARD_GAP)
            max_height = work.bottom() - y - reserved
            preferred = widget.preferred_height()  # type: ignore[attr-defined]
            height = max(1, min(preferred, max_height))
            widget.setGeometry(x, y, CARD_WIDTH, height)
            hwnd = wintypes.HWND(int(widget.winId()))
            self._user32.SetWindowPos(
                hwnd,
                wintypes.HWND(0),
                x,
                y,
                CARD_WIDTH,
                height,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            y += height + CARD_GAP

    def _find_workerw(self) -> int:
        user32 = self._user32
        progman = user32.FindWindowW("Progman", None)
        if not progman:
            return 0
        found = ctypes.c_void_p(0)

        @WNDENUMPROC
        def enum_proc(hwnd: int, _lparam: int) -> bool:
            shell = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if shell:
                found.value = user32.FindWindowExW(None, hwnd, "WorkerW", None)
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
