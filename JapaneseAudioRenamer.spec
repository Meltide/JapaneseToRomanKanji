# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file builds for the CLI and Tkinter GUI."""

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


def make_analysis(entry_point: str) -> Analysis:
    return Analysis(
        [entry_point],
        pathex=[],
        binaries=list(binaries),
        datas=list(datas),
        hiddenimports=list(hiddenimports),
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
    )


# Console executable: same CLI as before.
cli_analysis = make_analysis("rename_audio.py")
cli_pyz = PYZ(cli_analysis.pure)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    cli_analysis.binaries,
    cli_analysis.datas,
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

# Windowed executable: double-click launches the Tkinter GUI.
gui_analysis = make_analysis("gui.py")
gui_pyz = PYZ(gui_analysis.pure)
gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    gui_analysis.binaries,
    gui_analysis.datas,
    [],
    name="JapaneseAudioRenamerGUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
