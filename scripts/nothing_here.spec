# PyInstaller spec for Windows release builds.
# Run from repo root: pyinstaller scripts/nothing_here.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
root = Path(SPECPATH).resolve().parent
icon_file = str(root / "assets" / "app.ico")

datas = [
    (str(root / "data" / "ielts.json"), "data"),
    (str(root / "data" / "cet4.json"), "data"),
    (str(root / "data" / "cet6.json"), "data"),
    (str(root / "data" / "ky.json"), "data"),
    (str(root / "data" / "jp_n5.json"), "data"),
    (str(root / "data" / "jp_n4.json"), "data"),
    (str(root / "data" / "jp_n3.json"), "data"),
    (str(root / "data" / "jp_n2.json"), "data"),
    (str(root / "data" / "jp_n1.json"), "data"),
    (str(root / "src" / "nothing_here" / "ui" / "rose.svg"), str(Path("nothing_here") / "ui")),
    (str(root / "src" / "nothing_here" / "ui" / "loaf_board.html"), str(Path("nothing_here") / "ui")),
]
binaries = []
hiddenimports = [
    "nothing_here.app",
    "nothing_here.ui.card_window",
    "nothing_here.ui.tray",
    "nothing_here.ui.loaf_board",
    "PyQt6.QtSvg",
    "PyQt6.QtWebChannel",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
]


def _collect_webengine() -> None:
    import PyQt6

    for package in (
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
    ):
        extra_datas, extra_binaries, extra_hidden = collect_all(package)
        datas.extend(extra_datas)
        binaries.extend(extra_binaries)
        hiddenimports.extend(extra_hidden)
    qt6 = Path(PyQt6.__file__).resolve().parent / "Qt6"
    dest = str(Path("PyQt6") / "Qt6" / "bin")
    process = qt6 / "bin" / "QtWebEngineProcess.exe"
    if process.is_file():
        binaries.append((str(process), dest))
    for pattern in (
        "d3dcompiler_*.dll",
        "avcodec-*.dll",
        "avformat-*.dll",
        "avutil-*.dll",
        "swresample-*.dll",
        "swscale-*.dll",
        "Qt6Pdf.dll",
    ):
        for item in (qt6 / "bin").glob(pattern):
            binaries.append((str(item), dest))
    resources = qt6 / "resources"
    if resources.is_dir():
        datas.append((str(resources), str(Path("PyQt6") / "Qt6" / "resources")))
    locales = qt6 / "translations" / "qtwebengine_locales"
    if locales.is_dir():
        datas.append((str(locales), str(Path("PyQt6") / "Qt6" / "translations" / "qtwebengine_locales")))
    core = qt6 / "bin" / "Qt6Core.dll"
    engine = qt6 / "bin" / "Qt6WebEngineCore.dll"
    if core.is_file() and engine.is_file():
        core_ver = _win_file_version(core)
        engine_ver = _win_file_version(engine)
        if core_ver[:2] != engine_ver[:2]:
            raise SystemExit(
                f"Qt version mismatch: Qt6Core {core_ver} vs Qt6WebEngineCore {engine_ver}. "
                "Pin PyQt6 and PyQt6-WebEngine to the same minor version."
            )


def _win_file_version(path: Path) -> tuple[int, int, int, int]:
    import ctypes

    class _VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32),
            ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32),
            ("dwFileVersionLS", ctypes.c_uint32),
            ("dwProductVersionMS", ctypes.c_uint32),
            ("dwProductVersionLS", ctypes.c_uint32),
            ("dwFileFlagsMask", ctypes.c_uint32),
            ("dwFileFlags", ctypes.c_uint32),
            ("dwFileOS", ctypes.c_uint32),
            ("dwFileType", ctypes.c_uint32),
            ("dwFileSubtype", ctypes.c_uint32),
            ("dwFileDateMS", ctypes.c_uint32),
            ("dwFileDateLS", ctypes.c_uint32),
        ]

    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return (0, 0, 0, 0)
    buf = ctypes.create_string_buffer(size)
    ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buf)
    value = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(value), ctypes.byref(length)):
        return (0, 0, 0, 0)
    info = ctypes.cast(value, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
    return (
        info.dwFileVersionMS >> 16,
        info.dwFileVersionMS & 0xFFFF,
        info.dwFileVersionLS >> 16,
        info.dwFileVersionLS & 0xFFFF,
    )


_collect_webengine()

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

if not any("qtwebengineprocess" in str(item[0]).lower() for item in (*a.binaries, *a.datas)):
    raise SystemExit(
        "QtWebEngineProcess.exe was not collected. Install PyQt6-WebEngine before packing."
    )

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NothingHere",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NothingHere",
)
