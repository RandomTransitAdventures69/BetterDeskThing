# -*- mode: python ; coding: utf-8 -*-
# Onedir build: dist/MyDeskThing/MyDeskThing.exe
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [
    ("index.html", "."),
    (".env.example", "."),
    ("requirements.txt", "."),
    ("README.md", "."),
]
datas += collect_data_files("tzdata")

hiddenimports = [
    "config",
    "server",
    "server_manager",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "websockets",
    "requests",
    "spotipy",
    "dotenv",
    "anyio",
    "tzdata",
]
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("spotipy")

a = Analysis(
    ["setup_wizard.py"],
    pathex=["."],
    binaries=[],
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MyDeskThing",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
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
    name="MyDeskThing",
)
