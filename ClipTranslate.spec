# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

# Collect resource files so they are bundled into the output folder
resource_dir = Path(SPECPATH) / "resource"
added_files = []
if resource_dir.exists():
    for item in resource_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(SPECPATH)
            added_files.append((str(item), str(rel_path.parent)))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'customtkinter',
        'keyboard',
        'pyperclip',
        'pystray',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'PIL',
        'windows_toasts',
        'tencentcloud.common',
        'tencentcloud.common.common_client',
        'tencentcloud.common.credential',
        'tencentcloud.common.profile.client_profile',
        'tencentcloud.common.profile.http_profile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ClipTranslate',
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
    icon=['resource/logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ClipTranslate',
)
