# PyInstaller spec for Windows release builds.
# Run from repo root: pyinstaller scripts/nothing_here.spec

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent

datas = [
    (str(root / "data" / "ielts.json"), "data"),
    (str(root / "data" / "cet4.json"), "data"),
    (str(root / "data" / "cet6.json"), "data"),
    (str(root / "data" / "ky.json"), "data"),
    (str(root / "src" / "nothing_here" / "ui" / "rose.svg"), str(Path("nothing_here") / "ui")),
]

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "nothing_here.app",
        "nothing_here.ui.card_window",
        "nothing_here.ui.tray",
        "PyQt6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NothingHere",
)
