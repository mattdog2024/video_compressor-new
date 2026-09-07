# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller打包配置 - 万能视频压缩器"""

import os
import sys

block_cipher = None

# 项目根目录
project_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(project_dir, 'main.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[
        # 内嵌FFmpeg二进制
        (os.path.join(project_dir, 'assets', 'ffmpeg', 'ffmpeg.exe'), 'assets/ffmpeg'),
        (os.path.join(project_dir, 'assets', 'ffmpeg', 'ffprobe.exe'), 'assets/ffmpeg'),
        # 图标
        (os.path.join(project_dir, 'assets', 'icon.ico'), 'assets'),
    ],
    hiddenimports=[
        'gui',
        'gui.app',
        'gui.widgets',
        'gui.themes',
        'core',
        'core.ffmpeg_engine',
        'core.hardware',
        'core.subtitle',
        'core.probe',
        'utils',
        'utils.helpers',
        'windnd',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL.ImageTk', 'PIL.ImageDraw',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VideoCompressor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'assets', 'icon.ico'),
    version=os.path.join(project_dir, 'version_info.txt') if os.path.exists(os.path.join(project_dir, 'version_info.txt')) else None,
)
