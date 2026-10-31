# Wayback-Recon Windows executable build specification.

from pathlib import Path
import ssl


project_root = str(Path(SPECPATH).parent)
# Some Python distributions ship SSL policy data beside ssl.py. Preserve it
# when freezing that runtime rather than weakening certificate validation.
ssl_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
runtime_data = [(str(ssl_policy), '.')] if ssl_policy.is_file() else []

a = Analysis(
    [str(Path(project_root) / 'src' / 'app_entry.py')],
    pathex=[project_root],
    binaries=[],
    datas=runtime_data,
    hiddenimports=['dns.asyncbackend', 'dns._asyncio_backend'],
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
    a.binaries,
    a.datas,
    [],
    name='wayback_recon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
