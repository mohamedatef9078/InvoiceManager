# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path.cwd()


datas = [
    (
        str(project_dir / "templates"),
        "templates",
    ),
    (
        str(project_dir / "static"),
        "static",
    ),
]

fonts_dir = project_dir / "fonts"

if fonts_dir.exists():
    datas.append(
        (
            str(fonts_dir),
            "fonts",
        )
    )


a = Analysis(
    ["app.py"],
    pathex=[
        str(project_dir),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "flask",
        "jinja2",
        "werkzeug",
        "xlsxwriter",
        "reportlab",
        "qrcode",
        "PIL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


pyz = PYZ(
    a.pure,
)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InvoiceManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)


coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="InvoiceManager",
)