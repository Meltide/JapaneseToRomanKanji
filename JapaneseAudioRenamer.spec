# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build for the Windows executable."""

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [("data", "data")]
binaries = []
hiddenimports = []

for package in ("janome", "zhconv", "pykakasi", "jaconv"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# Some libraries use importlib.metadata at runtime to discover their version.
for package in ("janome", "pykakasi", "zhconv"):
    datas += copy_metadata(package)

a = Analysis(
    ["rename_audio.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JapaneseAudioRenamer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
