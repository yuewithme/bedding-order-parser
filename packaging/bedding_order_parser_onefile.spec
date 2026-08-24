# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path(SPECPATH).parent
source_root = project_root / "src"
package_root = source_root / "bedding_order_parser"
icon_path = package_root / "desktop" / "resources" / "app.ico"
version_path = Path(SPECPATH) / "version_info.txt"

datas = [
    (
        str(package_root / "web" / "templates"),
        "bedding_order_parser/web/templates",
    ),
    (
        str(package_root / "web" / "static"),
        "bedding_order_parser/web/static",
    ),
    (
        str(package_root / "desktop" / "resources"),
        "bedding_order_parser/desktop/resources",
    ),
]
hiddenimports = [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr",
    "pythonnet",
]

a = Analysis(
    [str(Path(SPECPATH) / "desktop_entry.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest.test"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="订单解析助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    icon=str(icon_path),
    version=str(version_path),
)
