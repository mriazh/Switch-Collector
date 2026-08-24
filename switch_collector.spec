# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone Unified Switch Collector portable build.

Produces an onedir bundle:

    dist/Switch-Collector/Switch-Collector.exe
    dist/Switch-Collector/_internal/

The collector resolves Netmiko drivers by *name* (``--device-types
hp_procurve,aruba_os``), so those imports are invisible to static analysis and
must be declared as hidden imports.
"""

import os

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = os.path.abspath(SPECPATH)

block_cipher = None

# Netmiko maps a device_type string to a driver class at runtime, so the driver
# packages are only imported dynamically. Bundle them all: an operator may pass
# any --device-types value, and a missing driver would fail at collection time.
hidden_imports = [
    "netmiko",
    "netmiko.cisco",
    "netmiko.hp",
    "netmiko.aruba",
    "netmiko.ssh_exception",
    "netmiko.utilities",
    "openpyxl",
    "openpyxl.styles",
    "openpyxl.utils",
    "paramiko",
    "paramiko.ssh_exception",
    "scp",
    "cryptography",
]
hidden_imports += collect_submodules("netmiko")

datas = collect_data_files("netmiko") + collect_data_files("openpyxl")

a = Analysis(
    ["switch_collector.py"],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Test-only and unrelated heavyweight packages bloat the bundle for nothing.
    excludes=["pytest", "hypothesis", "playwright", "tkinter", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

options = []

exe = EXE(
    pyz,
    a.scripts,
    options,
    exclude_binaries=True,
    name="Switch-Collector",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Switch-Collector",
)
